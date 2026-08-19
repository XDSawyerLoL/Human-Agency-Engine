from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256

import httpx
from sqlalchemy.orm import Session

from ..horizon_source_models import HorizonRawObservation, HorizonSource
from ..horizon_source_schemas import HorizonObservationIngest
from .horizon_sources import HorizonSourceService


METEOFRANCE_TOKEN_ENDPOINT = "https://portail-api.meteofrance.fr/token"
METEOFRANCE_VIGILANCE_ENDPOINT = (
    "https://public-api.meteofrance.fr/public/DPVigilance/v1/cartevigilance/encours"
)


def _utc_datetime(value: object) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _int_color(value: object) -> int:
    try:
        return max(0, min(4, int(value)))
    except (TypeError, ValueError):
        return 0


def _alert_snapshot(product: dict) -> list[dict]:
    alerts: list[dict] = []
    for period in product.get("periods", []) or []:
        if not isinstance(period, dict):
            continue
        timelaps = period.get("timelaps") or {}
        domains = timelaps.get("domain_ids", []) if isinstance(timelaps, dict) else []
        for domain in domains or []:
            if not isinstance(domain, dict):
                continue
            max_color = _int_color(domain.get("max_color_id"))
            if max_color < 2:
                continue
            phenomena = []
            for item in domain.get("phenomenon_items", []) or []:
                if not isinstance(item, dict):
                    continue
                phenomenon_color = _int_color(item.get("phenomenon_max_color_id"))
                if phenomenon_color < 2:
                    continue
                phenomena.append(
                    {
                        "phenomenon_id": str(item.get("phenomenon_id") or ""),
                        "max_color_id": phenomenon_color,
                        "timelaps": [
                            {
                                "begin_time": interval.get("begin_time"),
                                "end_time": interval.get("end_time"),
                                "color_id": _int_color(interval.get("color_id")),
                            }
                            for interval in (item.get("timelaps_items", []) or [])
                            if isinstance(interval, dict)
                        ],
                    }
                )
            alerts.append(
                {
                    "echeance": period.get("echeance"),
                    "begin_validity_time": period.get("begin_validity_time"),
                    "end_validity_time": period.get("end_validity_time"),
                    "domain_id": str(domain.get("domain_id") or ""),
                    "max_color_id": max_color,
                    "phenomena": phenomena,
                }
            )
    return alerts


class HorizonMeteoFranceService:
    USER_AGENT = "Human-Agency-Engine-HORIZON/0.1"

    def __init__(self, db: Session):
        self.db = db

    def _source(self) -> HorizonSource:
        HorizonSourceService(self.db).sync_builtin_sources()
        source = (
            self.db.query(HorizonSource)
            .filter(HorizonSource.source_key == "meteofrance-vigilance")
            .one()
        )
        if not source.enabled:
            raise ValueError("Météo-France Vigilance source is disabled")
        if source.adapter_kind != "meteofrance_vigilance_json":
            raise ValueError("Météo-France source adapter kind is not approved for live polling")
        return source

    @staticmethod
    def _basic_credential(application_id: str) -> str:
        value = application_id.strip()
        if value.lower().startswith("basic "):
            value = value[6:].strip()
        if not value:
            raise ValueError("METEOFRANCE_APPLICATION_ID is not configured")
        return value

    def poll(
        self,
        application_id: str,
        *,
        client: httpx.Client | None = None,
    ) -> dict:
        credential = self._basic_credential(application_id)
        source = self._source()
        owned_client = client is None
        if client is None:
            client = httpx.Client(
                timeout=httpx.Timeout(20.0),
                follow_redirects=False,
                headers={"User-Agent": self.USER_AGENT},
            )

        try:
            try:
                token_response = client.post(
                    METEOFRANCE_TOKEN_ENDPOINT,
                    data={"grant_type": "client_credentials"},
                    headers={
                        "Authorization": f"Basic {credential}",
                        "Accept": "application/json",
                    },
                )
                token_response.raise_for_status()
                token_payload = token_response.json()
                access_token = str(token_payload.get("access_token") or "").strip()
                if not access_token:
                    raise ValueError("Météo-France token response contains no access_token")

                response = client.get(
                    METEOFRANCE_VIGILANCE_ENDPOINT,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json",
                    },
                )
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise RuntimeError(f"Météo-France Vigilance poll failed: {str(exc)[:300]}") from exc
        finally:
            if owned_client:
                client.close()

        if not isinstance(payload, dict) or not isinstance(payload.get("product"), dict):
            raise RuntimeError("Météo-France Vigilance response has no product object")
        product = payload["product"]
        meta = product.get("meta") or {}
        if not isinstance(meta, dict):
            meta = {}
        snapshot_id = str(meta.get("snapshot_id") or "").strip()
        product_datetime = _utc_datetime(meta.get("product_datetime") or product.get("update_time"))
        generation_time = _utc_datetime(meta.get("generation_timestamp") or product.get("update_time"))
        if not snapshot_id:
            stable_basis = str(meta.get("product_datetime") or product.get("update_time") or payload)
            snapshot_id = f"derived-{sha256(stable_basis.encode('utf-8')).hexdigest()[:32]}"

        external_key = f"meteofrance-vigilance:{snapshot_id}"
        existing = self.db.query(HorizonRawObservation).filter(
            HorizonRawObservation.source_id == source.id,
            HorizonRawObservation.external_key == external_key,
        ).one_or_none()
        if existing is not None:
            return {
                "source_key": source.source_key,
                "configured": True,
                "new_observations": 0,
                "replayed_observations": 1,
                "observation_id": existing.id,
                "snapshot_id": snapshot_id,
                "global_max_color_id": existing.canonical_facts.get("global_max_color_id"),
                "active_alert_count": len(existing.canonical_facts.get("alerts", [])),
                "official_primary": True,
                "candidates_created": 0,
                "promoted_events": 0,
                "detection_is_confirmation": False,
            }

        alerts = _alert_snapshot(product)
        global_max_color = _int_color(product.get("global_max_color_id"))
        comments = []
        for period in product.get("periods", []) or []:
            if not isinstance(period, dict):
                continue
            text_items = period.get("text_items") or {}
            texts = text_items.get("text", []) if isinstance(text_items, dict) else []
            comments.extend(str(item) for item in (texts or []) if str(item).strip())

        observation = HorizonObservationIngest(
            external_key=external_key,
            observation_type="official_weather_vigilance",
            title=f"Météo-France Vigilance nationale niveau {global_max_color}",
            summary=" ".join(comments)[:4000],
            source_url="https://vigilance.meteofrance.fr/fr",
            geography=["FR"],
            canonical_facts={
                "snapshot_id": snapshot_id,
                "product_datetime": meta.get("product_datetime"),
                "generation_timestamp": meta.get("generation_timestamp"),
                "warning_type": product.get("warning_type"),
                "version_vigilance": product.get("version_vigilance"),
                "global_max_color_id": global_max_color,
                "alerts": alerts,
            },
            raw_metadata={
                "type_cdp": product.get("type_cdp"),
                "version_cdp": product.get("version_cdp"),
                "domain_id": product.get("domain_id"),
                "official_endpoint": METEOFRANCE_VIGILANCE_ENDPOINT,
            },
            event_time=product_datetime,
            published_at=generation_time,
            observed_at=datetime.now(timezone.utc),
        )
        row, created = HorizonSourceService(self.db).ingest_observation(source, observation)
        return {
            "source_key": source.source_key,
            "configured": True,
            "new_observations": 1 if created else 0,
            "replayed_observations": 0 if created else 1,
            "observation_id": row.id,
            "snapshot_id": snapshot_id,
            "global_max_color_id": global_max_color,
            "active_alert_count": len(alerts),
            "official_primary": True,
            # Normalization/candidate promotion remains a separate layer so department
            # scope is not lost before matching against the personal temporal twin.
            "candidates_created": 0,
            "promoted_events": 0,
            "detection_is_confirmation": False,
        }
