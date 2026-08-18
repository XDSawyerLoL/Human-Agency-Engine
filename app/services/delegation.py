from __future__ import annotations

import base64
import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from sqlalchemy.orm import Session

from ..acquisition_models import InformationNeed
from ..delegation_models import AgentSigningIdentity, DelegationGrant, DelegationUse
from ..delegation_schemas import DelegationConsume, DelegationIssue
from ..models import PersonalMandate, User
from ..synthesis_models import CandidateIntervention
from ..world_schemas import EventCreate
from .crypto import TokenCipher
from .world_model import WorldModelService

SAFE_CONSTRAINT_KEYS = {
    "max_amount",
    "currency",
    "category",
    "merchant",
    "reversible_only",
    "allowed_action_types",
    "jurisdiction",
    "purpose",
    "delivery_country",
}
ALLOWED_CAPABILITIES = {"inspect", "prepare", "execute_reversible"}
PROTOCOL = "hae-delegation-v1"


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64u_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _canonical(value: dict) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256(value: dict) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _token_hash(token: str) -> str:
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()


def _utc_epoch(value: datetime) -> int:
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return int(aware.timestamp())


def _public_jwk(identity: AgentSigningIdentity) -> dict:
    return {
        "kty": "OKP",
        "crv": "Ed25519",
        "x": identity.public_key_b64,
        "kid": identity.key_id,
        "use": "sig",
        "alg": "EdDSA",
    }


def _minimal_intervention(candidate: CandidateIntervention) -> dict:
    intervention = dict(candidate.intervention or {})
    intervention.pop("_candidate_id", None)
    return intervention


class DelegationService:
    def __init__(self, db: Session):
        self.db = db

    def ensure_identity(self, user: User) -> AgentSigningIdentity:
        identity = (
            self.db.query(AgentSigningIdentity)
            .filter(
                AgentSigningIdentity.user_id == user.id,
                AgentSigningIdentity.revoked_at.is_(None),
            )
            .order_by(AgentSigningIdentity.created_at.desc())
            .first()
        )
        if identity:
            return identity
        return self._create_identity(user)

    def _create_identity(self, user: User) -> AgentSigningIdentity:
        private_key = Ed25519PrivateKey.generate()
        private_raw = private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_raw = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        cipher = TokenCipher()
        identity = AgentSigningIdentity(
            user_id=user.id,
            key_id=uuid.uuid4().hex,
            algorithm="Ed25519",
            public_key_b64=_b64u(public_raw),
            encrypted_private_key=cipher.encrypt(_b64u(private_raw)),
        )
        self.db.add(identity)
        self.db.flush()
        WorldModelService(self.db).append_event(
            user,
            EventCreate(
                event_type="delegation.identity_created",
                source="delegation_service",
                subject_type="signing_identity",
                subject_id=identity.key_id,
                payload={"algorithm": identity.algorithm, "public_key": _public_jwk(identity)},
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(identity)
        return identity

    def rotate_identity(self, user: User, confirm: str) -> AgentSigningIdentity:
        required = f"ROTATE {user.external_id}"
        if confirm != required:
            raise ValueError(f"confirmation must equal: {required}")
        now = datetime.utcnow()
        identities = (
            self.db.query(AgentSigningIdentity)
            .filter(
                AgentSigningIdentity.user_id == user.id,
                AgentSigningIdentity.revoked_at.is_(None),
            )
            .all()
        )
        identity_ids = [item.id for item in identities]
        for identity in identities:
            identity.revoked_at = now
            identity.rotated_at = now
        if identity_ids:
            grants = (
                self.db.query(DelegationGrant)
                .filter(
                    DelegationGrant.identity_id.in_(identity_ids),
                    DelegationGrant.revoked_at.is_(None),
                )
                .all()
            )
            for grant in grants:
                grant.revoked_at = now
                grant.revocation_reason = "signing identity rotated"
        self.db.commit()
        new_identity = self._create_identity(user)
        WorldModelService(self.db).append_event(
            user,
            EventCreate(
                event_type="delegation.identity_rotated",
                source="user",
                subject_type="signing_identity",
                subject_id=new_identity.key_id,
                payload={"revoked_identity_count": len(identities)},
            ),
        )
        return new_identity

    def issue(self, user: User, request: DelegationIssue) -> tuple[DelegationGrant, dict]:
        if request.capability not in ALLOWED_CAPABILITIES:
            raise ValueError("unsupported capability")
        if request.audience.strip() in {"", "*"}:
            raise ValueError("delegation requires a specific audience")
        required = f"ISSUE {request.candidate_id} {request.capability}"
        if request.confirm != required:
            raise ValueError(f"confirmation must equal: {required}")

        candidate = (
            self.db.query(CandidateIntervention)
            .filter(
                CandidateIntervention.id == request.candidate_id,
                CandidateIntervention.user_id == user.id,
            )
            .one_or_none()
        )
        if not candidate:
            raise ValueError("candidate not found for user")
        if candidate.status != "ready_for_review":
            raise ValueError("candidate must pass CARE + FUTURE + Decision Lab before delegation")

        unresolved = (
            self.db.query(InformationNeed)
            .filter(
                InformationNeed.candidate_id == candidate.id,
                InformationNeed.blocks_candidate == True,  # noqa: E712
                InformationNeed.status == "open",
            )
            .count()
        )
        if unresolved:
            raise ValueError("candidate still has blocking information needs")

        mandate = (
            self.db.query(PersonalMandate)
            .filter(PersonalMandate.user_id == user.id)
            .one_or_none()
        )
        if not mandate:
            raise ValueError("Personal Mandate must be configured before delegation")

        intervention = _minimal_intervention(candidate)
        if request.capability == "execute_reversible":
            if intervention.get("reversible") is not True:
                raise ValueError("execute_reversible requires an explicitly reversible intervention")
            if not bool((mandate.autonomy or {}).get("allow_execute_reversible", False)):
                raise ValueError("Personal Mandate does not allow execute_reversible")
            if not request.execute_ack:
                raise ValueError("execute_reversible requires explicit execute_ack")
            if request.max_uses != 1:
                raise ValueError("execute_reversible grants are strictly single-use")

        constraints = self._validate_constraints(request.constraints)
        if request.capability == "execute_reversible":
            constraints["reversible_only"] = True

        identity = self.ensure_identity(user)
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=request.expires_in_seconds)
        grant_id = uuid.uuid4().hex
        subject_ref = uuid.uuid4().hex
        nonce = secrets.token_urlsafe(24)
        action_fingerprint = _sha256(intervention)
        action_type = str(intervention.get("type", ""))[:96]

        payload = {
            "iss": f"hae:{identity.key_id}",
            "sub": subject_ref,
            "aud": request.audience,
            "jti": grant_id,
            "iat": _utc_epoch(now),
            "exp": _utc_epoch(expires_at),
            "protocol": PROTOCOL,
            "capability": request.capability,
            "action": {
                "type": action_type,
                "fingerprint": action_fingerprint,
            },
            "candidate": {"fingerprint": candidate.candidate_key},
            "constraints": constraints,
            "mandate": {"version": mandate.version},
            "max_uses": request.max_uses,
            "nonce": nonce,
        }
        token = self._sign(identity, payload)
        grant = DelegationGrant(
            user_id=user.id,
            identity_id=identity.id,
            candidate_id=candidate.id,
            grant_id=grant_id,
            subject_ref=subject_ref,
            audience=request.audience,
            capability=request.capability,
            mandate_version=mandate.version,
            action_type=action_type,
            action_fingerprint=action_fingerprint,
            constraints=constraints,
            nonce=nonce,
            max_uses=request.max_uses,
            token_hash=_token_hash(token),
            issued_at=now,
            expires_at=expires_at,
        )
        self.db.add(grant)
        self.db.flush()
        WorldModelService(self.db).append_event(
            user,
            EventCreate(
                event_type="delegation.grant_issued",
                source="user",
                subject_type="delegation_grant",
                subject_id=grant.grant_id,
                payload={
                    "candidate_id": candidate.id,
                    "capability": grant.capability,
                    "audience": grant.audience,
                    "mandate_version": grant.mandate_version,
                    "expires_at": grant.expires_at.isoformat(),
                    "max_uses": grant.max_uses,
                },
                correlation_id=f"candidate:{candidate.id}",
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(grant)
        return grant, {
            "token": token,
            "public_jwk": _public_jwk(identity),
            "claims": payload,
        }

    def verify(self, token: str, audience: str | None = None) -> dict:
        header, claims, identity = self._verify_signature(token)
        grant = (
            self.db.query(DelegationGrant)
            .filter(DelegationGrant.grant_id == claims.get("jti"))
            .one_or_none()
        )
        self._validate_registered_grant(grant, identity, claims, token, audience)
        return {
            "valid": True,
            "header": header,
            "claims": claims,
            "grant": grant,
            "public_jwk": _public_jwk(identity),
        }

    def consume(self, request: DelegationConsume) -> DelegationUse:
        header, claims, identity = self._verify_signature(request.token)
        grant = (
            self.db.query(DelegationGrant)
            .filter(DelegationGrant.grant_id == claims.get("jti"))
            .with_for_update()
            .one_or_none()
        )
        self._validate_registered_grant(
            grant,
            identity,
            claims,
            request.token,
            request.audience,
        )
        claimed_fingerprint = claims.get("action", {}).get("fingerprint")
        if request.action_fingerprint and request.action_fingerprint != claimed_fingerprint:
            raise ValueError("requested action fingerprint does not match delegation")
        existing = (
            self.db.query(DelegationUse)
            .filter(
                DelegationUse.grant_id == grant.id,
                DelegationUse.request_id == request.request_id,
            )
            .one_or_none()
        )
        if existing:
            raise ValueError("delegation request_id has already been consumed")
        if grant.use_count >= grant.max_uses:
            raise ValueError("delegation grant is exhausted")

        use = DelegationUse(
            grant_id=grant.id,
            request_id=request.request_id,
            audience=request.audience,
            action_fingerprint=claimed_fingerprint,
            metadata_json=request.metadata_json,
        )
        self.db.add(use)
        grant.use_count += 1
        self.db.flush()
        user = self.db.query(User).filter(User.id == grant.user_id).one()
        WorldModelService(self.db).append_event(
            user,
            EventCreate(
                event_type="delegation.grant_consumed",
                source="delegation_service",
                subject_type="delegation_grant",
                subject_id=grant.grant_id,
                payload={
                    "request_id": request.request_id,
                    "audience": request.audience,
                    "use_count": grant.use_count,
                    "max_uses": grant.max_uses,
                },
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(use)
        return use

    def revoke(self, user: User, grant: DelegationGrant, reason: str) -> DelegationGrant:
        if grant.user_id != user.id:
            raise ValueError("delegation grant does not belong to user")
        if grant.revoked_at is None:
            grant.revoked_at = datetime.utcnow()
            grant.revocation_reason = reason
            WorldModelService(self.db).append_event(
                user,
                EventCreate(
                    event_type="delegation.grant_revoked",
                    source="user",
                    subject_type="delegation_grant",
                    subject_id=grant.grant_id,
                    payload={"reason": reason},
                ),
                commit=False,
            )
            self.db.commit()
            self.db.refresh(grant)
        return grant

    def _validate_registered_grant(
        self,
        grant: DelegationGrant | None,
        identity: AgentSigningIdentity,
        claims: dict,
        token: str,
        audience: str | None,
    ) -> None:
        presented_hash = _token_hash(token)
        if not grant or not secrets.compare_digest(grant.token_hash, presented_hash):
            raise ValueError("delegation grant is not registered")
        if grant.identity_id != identity.id:
            raise ValueError("delegation signing identity mismatch")
        if identity.revoked_at is not None:
            raise ValueError("signing identity is revoked")
        if grant.revoked_at is not None:
            raise ValueError("delegation grant is revoked")
        now = datetime.utcnow()
        if grant.expires_at <= now or int(claims.get("exp", 0)) <= _utc_epoch(now):
            raise ValueError("delegation grant is expired")
        if audience is not None and audience != grant.audience:
            raise ValueError("delegation audience mismatch")
        if claims.get("aud") != grant.audience:
            raise ValueError("signed audience does not match registered grant")
        if grant.use_count >= grant.max_uses:
            raise ValueError("delegation grant is exhausted")

        mandate = (
            self.db.query(PersonalMandate)
            .filter(PersonalMandate.user_id == grant.user_id)
            .one_or_none()
        )
        if not mandate or mandate.version != grant.mandate_version:
            raise ValueError("delegation grant is stale because Personal Mandate changed")
        if claims.get("mandate", {}).get("version") != grant.mandate_version:
            raise ValueError("signed mandate version mismatch")
        if claims.get("action", {}).get("fingerprint") != grant.action_fingerprint:
            raise ValueError("signed action fingerprint mismatch")
        if claims.get("capability") != grant.capability:
            raise ValueError("signed capability mismatch")
        if claims.get("jti") != grant.grant_id:
            raise ValueError("signed grant identifier mismatch")
        if claims.get("nonce") != grant.nonce:
            raise ValueError("signed nonce mismatch")
        if int(claims.get("max_uses", 0)) != grant.max_uses:
            raise ValueError("signed max_uses mismatch")

    def _sign(self, identity: AgentSigningIdentity, claims: dict) -> str:
        header = {
            "alg": "EdDSA",
            "kid": identity.key_id,
            "typ": "HAE-Delegation+JWT",
        }
        header_b64 = _b64u(_canonical(header))
        payload_b64 = _b64u(_canonical(claims))
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        private_raw = _b64u_decode(TokenCipher().decrypt(identity.encrypted_private_key))
        private_key = Ed25519PrivateKey.from_private_bytes(private_raw)
        signature = private_key.sign(signing_input)
        return f"{header_b64}.{payload_b64}.{_b64u(signature)}"

    def _verify_signature(self, token: str) -> tuple[dict, dict, AgentSigningIdentity]:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("invalid compact JWS")
        try:
            header = json.loads(_b64u_decode(parts[0]))
            claims = json.loads(_b64u_decode(parts[1]))
            signature = _b64u_decode(parts[2])
        except Exception as exc:
            raise ValueError("invalid compact JWS encoding") from exc
        if header.get("alg") != "EdDSA" or header.get("typ") != "HAE-Delegation+JWT":
            raise ValueError("unsupported delegation JWS header")
        if claims.get("protocol") != PROTOCOL:
            raise ValueError("unsupported delegation protocol")
        key_id = str(header.get("kid", ""))
        identity = (
            self.db.query(AgentSigningIdentity)
            .filter(AgentSigningIdentity.key_id == key_id)
            .one_or_none()
        )
        if not identity:
            raise ValueError("unknown signing key")
        public_key = Ed25519PublicKey.from_public_bytes(_b64u_decode(identity.public_key_b64))
        try:
            public_key.verify(signature, f"{parts[0]}.{parts[1]}".encode("ascii"))
        except InvalidSignature as exc:
            raise ValueError("invalid delegation signature") from exc
        return header, claims, identity

    def _validate_constraints(self, constraints: dict) -> dict:
        unknown = sorted(set(constraints) - SAFE_CONSTRAINT_KEYS)
        if unknown:
            raise ValueError(
                "unsupported or over-disclosing constraint keys: " + ", ".join(unknown)
            )
        cleaned = dict(constraints)
        if "max_amount" in cleaned:
            value = cleaned["max_amount"]
            if not isinstance(value, (int, float)) or value < 0:
                raise ValueError("max_amount must be a non-negative number")
        if "reversible_only" in cleaned and not isinstance(cleaned["reversible_only"], bool):
            raise ValueError("reversible_only must be boolean")
        if "allowed_action_types" in cleaned:
            values = cleaned["allowed_action_types"]
            if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
                raise ValueError("allowed_action_types must be a list of strings")
        return cleaned
