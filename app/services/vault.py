from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from sqlalchemy.orm import Session

from ..allocation_models import CollectivePrivateAllocation
from ..delegation_models import AgentSigningIdentity
from ..models import User
from ..settlement_permit_models import PseudonymousSettlementPermit
from ..vault_models import SelectiveDisclosureGrant, SelectiveDisclosureUse, UserVaultClaim
from ..vault_schemas import DisclosureGrantConsume, DisclosureGrantIssue
from ..world_schemas import EventCreate
from .crypto import TokenCipher
from .policy import canonical_json, sha256_dict
from .settlement_permit import SettlementPermitService
from .world_model import WorldModelService

PROTOCOL = "hae-selective-disclosure-v1"
CAPABILITY = "reveal_fulfillment_claims"
MAX_USES = 1
ALLOWED_CLAIMS = {
    "delivery_name",
    "address_line1",
    "address_line2",
    "postal_code",
    "city",
    "country",
    "phone",
    "email",
}


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64u_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _token_hash(token: str) -> str:
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()


def _epoch(value: datetime) -> int:
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return int(aware.timestamp())


def _fingerprint(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_claim(claim_type: str, value: str) -> str:
    if claim_type not in ALLOWED_CLAIMS:
        raise ValueError("claim type is not allowed in fulfillment vault V1")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("vault claim value cannot be empty")
    limits = {
        "delivery_name": 120,
        "address_line1": 200,
        "address_line2": 200,
        "postal_code": 32,
        "city": 120,
        "country": 2,
        "phone": 40,
        "email": 254,
    }
    if len(cleaned) > limits[claim_type]:
        raise ValueError("vault claim value exceeds V1 length limit")
    if claim_type == "country":
        cleaned = cleaned.upper()
        if len(cleaned) != 2 or not cleaned.isalpha():
            raise ValueError("country must be a two-letter alphabetic code")
    return cleaned


def _claim_set_hash(claims: list[UserVaultClaim]) -> str:
    return sha256_dict(
        {
            "claims": [
                {
                    "claim_type": item.claim_type,
                    "value_fingerprint": item.value_fingerprint,
                    "version": item.version,
                }
                for item in sorted(claims, key=lambda row: row.claim_type)
            ]
        }
    )


class SelectiveDisclosureVaultService:
    def __init__(self, db: Session):
        self.db = db

    def store_claim(self, user: User, claim_type: str, value: str, confirm: str) -> UserVaultClaim:
        if claim_type not in ALLOWED_CLAIMS:
            raise ValueError("claim type is not allowed in fulfillment vault V1")
        required = f"STORE VAULT CLAIM {claim_type}"
        if confirm != required:
            raise ValueError(f"confirmation must equal: {required}")
        normalized = _normalize_claim(claim_type, value)
        cipher = TokenCipher()
        row = (
            self.db.query(UserVaultClaim)
            .filter(UserVaultClaim.user_id == user.id, UserVaultClaim.claim_type == claim_type)
            .one_or_none()
        )
        if row:
            row.encrypted_value = cipher.encrypt(normalized)
            row.value_fingerprint = _fingerprint(normalized)
            row.version += 1
            row.status = "active"
            row.updated_at = datetime.utcnow()
        else:
            row = UserVaultClaim(
                user_id=user.id,
                claim_type=claim_type,
                encrypted_value=cipher.encrypt(normalized),
                value_fingerprint=_fingerprint(normalized),
                version=1,
                status="active",
            )
            self.db.add(row)
        self.db.flush()
        WorldModelService(self.db).append_event(
            user,
            EventCreate(
                event_type="vault.claim_stored",
                source="user",
                subject_type="vault_claim",
                subject_id=f"{claim_type}:v{row.version}",
                payload={
                    "claim_type": claim_type,
                    "value_fingerprint": row.value_fingerprint,
                    "version": row.version,
                    "raw_value_logged": False,
                },
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_claim(self, user: User, claim_type: str, confirm: str) -> None:
        required = f"DELETE VAULT CLAIM {claim_type}"
        if confirm != required:
            raise ValueError(f"confirmation must equal: {required}")
        row = (
            self.db.query(UserVaultClaim)
            .filter(UserVaultClaim.user_id == user.id, UserVaultClaim.claim_type == claim_type)
            .one_or_none()
        )
        if not row:
            return
        self.db.delete(row)
        self.db.commit()

    def _claims_for_user(self, user: User, claim_types: list[str]) -> list[UserVaultClaim]:
        normalized_types = sorted(set(claim_types))
        if not normalized_types:
            raise ValueError("at least one claim type is required")
        unsupported = [item for item in normalized_types if item not in ALLOWED_CLAIMS]
        if unsupported:
            raise ValueError("unsupported disclosure claim type: " + ", ".join(unsupported))
        rows = (
            self.db.query(UserVaultClaim)
            .filter(
                UserVaultClaim.user_id == user.id,
                UserVaultClaim.claim_type.in_(normalized_types),
                UserVaultClaim.status == "active",
            )
            .all()
        )
        by_type = {item.claim_type: item for item in rows}
        missing = [item for item in normalized_types if item not in by_type]
        if missing:
            raise ValueError("missing configured vault claims: " + ", ".join(missing))
        return [by_type[item] for item in normalized_types]

    def issue(self, user: User, request: DisclosureGrantIssue) -> tuple[SelectiveDisclosureGrant, dict]:
        permit = (
            self.db.query(PseudonymousSettlementPermit)
            .filter(PseudonymousSettlementPermit.permit_id == request.settlement_permit_id)
            .one_or_none()
        )
        if not permit or permit.user_id != user.id:
            raise ValueError("consumed settlement permit not found for user")
        if permit.status != "consumed" or permit.use_count != 1 or permit.consumed_at is None:
            raise ValueError("settlement permit must be consumed before fulfillment disclosure")

        private = (
            self.db.query(CollectivePrivateAllocation)
            .filter(CollectivePrivateAllocation.id == permit.private_allocation_id)
            .one()
        )
        context = SettlementPermitService(self.db)._current_context(user, private)
        _round_row, offer, _commitment, decision, _envelope, mandate, receipt, audience = context
        if audience != permit.audience:
            raise ValueError("settlement responder changed before disclosure")
        if receipt.id != permit.settlement_receipt_id:
            raise ValueError("settlement readiness changed before disclosure")
        if decision.decision_hash != permit.decision_hash:
            raise ValueError("allocation acceptance changed before disclosure")
        if mandate.version != permit.mandate_version:
            raise ValueError("Personal Mandate changed before disclosure")

        claims = self._claims_for_user(user, request.claim_types)
        claim_set_hash = _claim_set_hash(claims)
        required = f"ISSUE DISCLOSURE {permit.permit_id} {claim_set_hash[-12:]}"
        if request.confirm != required:
            raise ValueError(f"confirmation must equal: {required}")
        existing = (
            self.db.query(SelectiveDisclosureGrant)
            .filter(SelectiveDisclosureGrant.settlement_permit_id == permit.id)
            .one_or_none()
        )
        if existing:
            raise ValueError("a disclosure grant was already issued for this settlement permit")

        identity = (
            self.db.query(AgentSigningIdentity)
            .filter(AgentSigningIdentity.id == permit.signing_identity_id)
            .one()
        )
        if identity.revoked_at is not None:
            raise ValueError("user signing identity is revoked")
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=request.expires_in_seconds)
        grant_id = uuid.uuid4().hex
        subject_ref = uuid.uuid4().hex
        claim_types = [item.claim_type for item in claims]
        payload = {
            "iss": f"hae:{identity.key_id}",
            "sub": subject_ref,
            "aud": permit.audience,
            "jti": grant_id,
            "iat": _epoch(now),
            "exp": _epoch(expires_at),
            "protocol": PROTOCOL,
            "capability": CAPABILITY,
            "parent": {
                "settlement_permit_id": permit.permit_id,
                "readiness_hash": permit.readiness_hash,
                "offer_hash": offer.offer_hash,
            },
            "claims": {
                "types": claim_types,
                "set_hash": claim_set_hash,
            },
            "mandate": {"version": mandate.version},
            "max_uses": MAX_USES,
            "nonce": secrets.token_urlsafe(24),
        }
        token = self._sign(identity, payload)
        grant = SelectiveDisclosureGrant(
            user_id=user.id,
            settlement_permit_id=permit.id,
            signing_identity_id=identity.id,
            grant_id=grant_id,
            subject_ref=subject_ref,
            audience=permit.audience,
            claim_types=claim_types,
            claim_set_hash=claim_set_hash,
            token_hash=_token_hash(token),
            status="active",
            use_count=0,
            issued_at=now,
            expires_at=expires_at,
        )
        self.db.add(grant)
        self.db.flush()
        WorldModelService(self.db).append_event(
            user,
            EventCreate(
                event_type="vault.disclosure_grant_issued",
                source="user",
                subject_type="selective_disclosure_grant",
                subject_id=grant.grant_id,
                payload={
                    "audience": grant.audience,
                    "claim_types": grant.claim_types,
                    "claim_set_hash": grant.claim_set_hash,
                    "raw_values_logged": False,
                    "payment_claims_allowed": False,
                    "external_dispatch": False,
                },
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(grant)
        return grant, {"token": token, "claims": payload, "public_jwk": self._public_jwk(identity)}

    def verify(self, token: str, audience: str) -> dict:
        header, claims, identity = self._verify_signature(token)
        grant = (
            self.db.query(SelectiveDisclosureGrant)
            .filter(SelectiveDisclosureGrant.grant_id == claims.get("jti"))
            .one_or_none()
        )
        self._validate_registered(grant, identity, claims, token, audience)
        return {
            "valid": True,
            "claims": claims,
            "public_jwk": self._public_jwk(identity),
            "raw_values_in_proof": False,
            "payment_claims_allowed": False,
            "external_dispatch": False,
        }

    def consume(self, request: DisclosureGrantConsume) -> tuple[SelectiveDisclosureUse, dict]:
        header, claims, identity = self._verify_signature(request.token)
        grant = (
            self.db.query(SelectiveDisclosureGrant)
            .filter(SelectiveDisclosureGrant.grant_id == claims.get("jti"))
            .with_for_update()
            .one_or_none()
        )
        self._validate_registered(grant, identity, claims, request.token, request.audience)
        if grant.use_count >= MAX_USES:
            raise ValueError("disclosure grant is exhausted")
        existing = (
            self.db.query(SelectiveDisclosureUse)
            .filter(
                SelectiveDisclosureUse.grant_db_id == grant.id,
                SelectiveDisclosureUse.request_id == request.request_id,
            )
            .one_or_none()
        )
        if existing:
            raise ValueError("disclosure request_id has already been consumed")

        user = self.db.query(User).filter(User.id == grant.user_id).one()
        rows = self._claims_for_user(user, list(grant.claim_types))
        if _claim_set_hash(rows) != grant.claim_set_hash:
            raise ValueError("vault claims changed after disclosure authorization")
        cipher = TokenCipher()
        disclosed = {item.claim_type: cipher.decrypt(item.encrypted_value) for item in rows}
        use = SelectiveDisclosureUse(
            grant_db_id=grant.id,
            request_id=request.request_id,
            audience=request.audience,
            disclosed_claim_types=list(grant.claim_types),
        )
        self.db.add(use)
        grant.use_count = 1
        grant.status = "consumed"
        grant.consumed_at = datetime.utcnow()
        self.db.flush()
        WorldModelService(self.db).append_event(
            user,
            EventCreate(
                event_type="vault.disclosure_consumed",
                source="fulfillment_adapter_boundary",
                subject_type="selective_disclosure_grant",
                subject_id=grant.grant_id,
                payload={
                    "request_id": request.request_id,
                    "claim_types": list(grant.claim_types),
                    "raw_values_logged": False,
                    "external_dispatch": False,
                    "payment_created": False,
                    "order_created": False,
                },
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(use)
        return use, disclosed

    def revoke(self, user: User, grant: SelectiveDisclosureGrant, confirm: str):
        if grant.user_id != user.id:
            raise ValueError("disclosure grant does not belong to user")
        required = f"REVOKE DISCLOSURE {grant.grant_id}"
        if confirm != required:
            raise ValueError(f"confirmation must equal: {required}")
        if grant.status == "consumed":
            raise ValueError("consumed disclosure cannot be revoked retroactively")
        if grant.revoked_at is None:
            grant.status = "revoked"
            grant.revoked_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(grant)
        return grant

    def _validate_registered(
        self,
        grant: SelectiveDisclosureGrant | None,
        identity: AgentSigningIdentity,
        claims: dict,
        token: str,
        audience: str,
    ) -> None:
        if not grant:
            raise ValueError("disclosure grant is not registered")
        if not hmac.compare_digest(grant.token_hash, _token_hash(token)):
            raise ValueError("disclosure bearer token does not match registry")
        if grant.signing_identity_id != identity.id or identity.revoked_at is not None:
            raise ValueError("disclosure signing identity is invalid")
        if grant.status != "active" or grant.revoked_at is not None:
            raise ValueError("disclosure grant is not active")
        now = datetime.utcnow()
        if grant.expires_at <= now or int(claims.get("exp", 0)) <= _epoch(now):
            raise ValueError("disclosure grant is expired")
        if grant.use_count >= MAX_USES:
            raise ValueError("disclosure grant is exhausted")
        if audience != grant.audience or claims.get("aud") != grant.audience:
            raise ValueError("disclosure audience mismatch")
        if claims.get("protocol") != PROTOCOL or claims.get("capability") != CAPABILITY:
            raise ValueError("unsupported disclosure protocol or capability")
        if claims.get("jti") != grant.grant_id or claims.get("sub") != grant.subject_ref:
            raise ValueError("disclosure identifiers do not match registry")
        if claims.get("claims", {}).get("types") != grant.claim_types:
            raise ValueError("disclosure claim types mismatch")
        if claims.get("claims", {}).get("set_hash") != grant.claim_set_hash:
            raise ValueError("disclosure claim-set hash mismatch")
        if int(claims.get("max_uses", 0)) != MAX_USES:
            raise ValueError("disclosure max_uses mismatch")

        user = self.db.query(User).filter(User.id == grant.user_id).one()
        permit = (
            self.db.query(PseudonymousSettlementPermit)
            .filter(PseudonymousSettlementPermit.id == grant.settlement_permit_id)
            .one()
        )
        if permit.status != "consumed" or permit.audience != grant.audience:
            raise ValueError("parent settlement permit is not in consumed preparation state")
        private = (
            self.db.query(CollectivePrivateAllocation)
            .filter(CollectivePrivateAllocation.id == permit.private_allocation_id)
            .one()
        )
        context = SettlementPermitService(self.db)._current_context(user, private)
        _round_row, offer, _commitment, decision, _envelope, mandate, receipt, current_audience = context
        if current_audience != grant.audience:
            raise ValueError("fulfillment responder changed after disclosure authorization")
        if receipt.id != permit.settlement_receipt_id or offer.offer_hash != permit.offer_hash:
            raise ValueError("settlement context changed after disclosure authorization")
        if decision.decision_hash != permit.decision_hash:
            raise ValueError("allocation acceptance changed after disclosure authorization")
        if int(claims.get("mandate", {}).get("version", 0)) != mandate.version:
            raise ValueError("Personal Mandate changed after disclosure authorization")
        rows = self._claims_for_user(user, list(grant.claim_types))
        if _claim_set_hash(rows) != grant.claim_set_hash:
            raise ValueError("vault claims changed after disclosure authorization")

    def _sign(self, identity: AgentSigningIdentity, claims: dict) -> str:
        cipher = TokenCipher()
        private_raw = _b64u_decode(cipher.decrypt(identity.encrypted_private_key))
        private_key = Ed25519PrivateKey.from_private_bytes(private_raw)
        header = {"alg": "EdDSA", "typ": "HAE-DISCLOSURE-GRANT", "kid": identity.key_id}
        encoded_header = _b64u(canonical_json(header))
        encoded_claims = _b64u(canonical_json(claims))
        signing_input = f"{encoded_header}.{encoded_claims}".encode("ascii")
        signature = private_key.sign(signing_input)
        return f"{encoded_header}.{encoded_claims}.{_b64u(signature)}"

    def _verify_signature(self, token: str):
        try:
            encoded_header, encoded_claims, encoded_signature = token.split(".")
            header = json.loads(_b64u_decode(encoded_header))
            claims = json.loads(_b64u_decode(encoded_claims))
            if header.get("alg") != "EdDSA" or header.get("typ") != "HAE-DISCLOSURE-GRANT":
                raise ValueError("unexpected disclosure header")
            identity = (
                self.db.query(AgentSigningIdentity)
                .filter(AgentSigningIdentity.key_id == header.get("kid"))
                .one_or_none()
            )
            if not identity:
                raise ValueError("unknown disclosure signing key")
            public_key = Ed25519PublicKey.from_public_bytes(_b64u_decode(identity.public_key_b64))
            public_key.verify(
                _b64u_decode(encoded_signature),
                f"{encoded_header}.{encoded_claims}".encode("ascii"),
            )
        except (ValueError, InvalidSignature, json.JSONDecodeError, TypeError) as exc:
            raise ValueError("invalid disclosure grant signature") from exc
        return header, claims, identity

    @staticmethod
    def _public_jwk(identity: AgentSigningIdentity) -> dict:
        return {
            "kty": "OKP",
            "crv": "Ed25519",
            "x": identity.public_key_b64,
            "kid": identity.key_id,
            "use": "sig",
            "alg": "EdDSA",
        }
