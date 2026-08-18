from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from ..config import settings
from ..models import ConnectorAccount, OAuthState, User
from ..services.crypto import TokenCipher
from ..services.ingestion import SignalIngestionService
from .base import NormalizedSignal

GMAIL_READONLY = "https://www.googleapis.com/auth/gmail.readonly"
CALENDAR_READONLY = "https://www.googleapis.com/auth/calendar.readonly"
SCOPES = [GMAIL_READONLY, CALENDAR_READONLY]


def _utcnow() -> datetime:
    return datetime.utcnow()


def _state_hash(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def _client_config() -> dict:
    if not settings.google_client_id or not settings.google_client_secret:
        raise RuntimeError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are required")
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }


def _flow(state: str | None = None) -> Flow:
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, state=state)
    flow.redirect_uri = settings.google_redirect_uri
    return flow


def _serialize_credentials(credentials: Credentials) -> str:
    payload = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": list(credentials.scopes or SCOPES),
    }
    if credentials.expiry:
        expiry = credentials.expiry
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        payload["expiry"] = expiry.isoformat()
    return json.dumps(payload)


def _deserialize_credentials(raw: str) -> Credentials:
    payload = json.loads(raw)
    expiry = payload.get("expiry")
    if expiry:
        parsed = datetime.fromisoformat(expiry)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        payload["expiry"] = parsed
    return Credentials(**payload)


def start_google_oauth(db: Session, user: User) -> str:
    state = secrets.token_urlsafe(32)
    db.add(
        OAuthState(
            state_hash=_state_hash(state),
            user_id=user.id,
            provider="google",
            expires_at=_utcnow() + timedelta(minutes=10),
        )
    )
    db.commit()

    authorization_url, _ = _flow(state=state).authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return authorization_url


def finish_google_oauth(db: Session, state: str, code: str) -> ConnectorAccount:
    record = (
        db.query(OAuthState)
        .filter(
            OAuthState.state_hash == _state_hash(state),
            OAuthState.provider == "google",
            OAuthState.consumed == False,  # noqa: E712
        )
        .one_or_none()
    )
    if not record or record.expires_at < _utcnow():
        raise ValueError("OAuth state is invalid or expired")

    flow = _flow(state=state)
    flow.fetch_token(code=code)
    credentials = flow.credentials

    account = (
        db.query(ConnectorAccount)
        .filter(
            ConnectorAccount.user_id == record.user_id,
            ConnectorAccount.provider == "google",
        )
        .one_or_none()
    )
    cipher = TokenCipher()
    encrypted = cipher.encrypt(_serialize_credentials(credentials))

    if account is None:
        account = ConnectorAccount(
            user_id=record.user_id,
            provider="google",
            encrypted_token_json=encrypted,
            scopes=list(credentials.scopes or SCOPES),
        )
        db.add(account)
    else:
        account.encrypted_token_json = encrypted
        account.scopes = list(credentials.scopes or SCOPES)
        account.enabled = True
        account.last_error = ""
        account.updated_at = _utcnow()

    record.consumed = True
    db.commit()
    db.refresh(account)
    return account


class GoogleReadOnlyConnector:
    provider = "google"

    def __init__(self, db: Session):
        self.db = db
        self.ingestion = SignalIngestionService(db)

    def _credentials(self, account: ConnectorAccount) -> Credentials:
        cipher = TokenCipher()
        credentials = _deserialize_credentials(cipher.decrypt(account.encrypted_token_json))
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            account.encrypted_token_json = cipher.encrypt(_serialize_credentials(credentials))
            account.updated_at = _utcnow()
            self.db.commit()
        return credentials

    def sync(self, account_id: int) -> dict:
        account = (
            self.db.query(ConnectorAccount)
            .filter(
                ConnectorAccount.id == account_id,
                ConnectorAccount.provider == "google",
                ConnectorAccount.enabled == True,  # noqa: E712
            )
            .one_or_none()
        )
        if not account:
            raise ValueError("Enabled Google connector not found")

        try:
            credentials = self._credentials(account)
            gmail_count = self._sync_gmail(account, credentials)
            calendar_count = self._sync_calendar(account, credentials)
            account.last_synced_at = _utcnow()
            account.last_error = ""
            account.updated_at = _utcnow()
            self.db.commit()
            return {
                "provider": "google",
                "gmail_signals": gmail_count,
                "calendar_signals": calendar_count,
                "total_signals": gmail_count + calendar_count,
            }
        except Exception as exc:
            self.db.rollback()
            account = self.db.query(ConnectorAccount).filter(ConnectorAccount.id == account_id).one()
            account.last_error = str(exc)[:1000]
            account.updated_at = _utcnow()
            self.db.commit()
            raise

    def _sync_gmail(self, account: ConnectorAccount, credentials: Credentials) -> int:
        service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        query = f"newer_than:{settings.google_sync_lookback_days}d"
        max_messages = max(1, settings.google_max_gmail_messages)

        message_ids: list[str] = []
        page_token: str | None = None
        while len(message_ids) < max_messages:
            response = (
                service.users()
                .messages()
                .list(
                    userId="me",
                    q=query,
                    maxResults=min(100, max_messages - len(message_ids)),
                    pageToken=page_token,
                )
                .execute()
            )
            message_ids.extend(item["id"] for item in response.get("messages", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        created = 0
        for message_id in message_ids:
            result = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=message_id,
                    format="metadata",
                    metadataHeaders=["Subject", "From", "Date"],
                )
                .execute()
            )
            headers = {
                item.get("name", "").lower(): item.get("value", "")
                for item in result.get("payload", {}).get("headers", [])
            }
            observed_at = _utcnow()
            if headers.get("date"):
                try:
                    parsed = parsedate_to_datetime(headers["date"])
                    if parsed.tzinfo:
                        observed_at = parsed.astimezone(timezone.utc).replace(tzinfo=None)
                except (TypeError, ValueError, OverflowError):
                    pass

            signal = NormalizedSignal(
                external_key=f"gmail:{message_id}",
                source="google:gmail",
                type="email_message",
                observed_at=observed_at,
                payload={
                    "message_id": message_id,
                    "thread_id": result.get("threadId"),
                    "subject": headers.get("subject", ""),
                    "sender": headers.get("from", ""),
                    "snippet": result.get("snippet", ""),
                    "labels": result.get("labelIds", []),
                },
            )
            if self.ingestion.ingest(account, signal):
                created += 1

        self.db.commit()
        return created

    def _sync_calendar(self, account: ConnectorAccount, credentials: Credentials) -> int:
        service = build("calendar", "v3", credentials=credentials, cache_discovery=False)
        start = datetime.now(timezone.utc)
        end = start + timedelta(days=settings.google_sync_lookahead_days)
        response = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=250,
            )
            .execute()
        )

        created = 0
        for event in response.get("items", []):
            event_id = event.get("id")
            if not event_id:
                continue
            start_data = event.get("start", {})
            start_value = start_data.get("dateTime") or start_data.get("date")
            signal = NormalizedSignal(
                external_key=f"calendar:{event_id}:{start_value}",
                source="google:calendar",
                type="calendar_event",
                observed_at=_utcnow(),
                payload={
                    "event_id": event_id,
                    "summary": event.get("summary", ""),
                    "description": event.get("description", "")[:2000],
                    "location": event.get("location", ""),
                    "start": start_value,
                    "end": event.get("end", {}).get("dateTime") or event.get("end", {}).get("date"),
                    "html_link": event.get("htmlLink"),
                    "status": event.get("status"),
                },
            )
            if self.ingestion.ingest(account, signal):
                created += 1

        self.db.commit()
        return created
