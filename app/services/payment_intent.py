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
from ..collective_offer_models import CollectiveMarketOffer
from ..delegation_models import AgentSigningIdentity
from ..models import PersonalMandate, User
from ..payment_intent_models import PaymentIntentCapability, PaymentIntentCapabilityUse
from ..payment_intent_schemas import PaymentIntentConsume, PaymentIntentIssue, PaymentIntentPreview
from ..settlement_permit_models import PseudonymousSettlementPermit
from ..world_schemas import EventCreate
from .crypto import TokenCipher
from .policy import canonical_json, sha256_dict
from .settlement_permit import SettlementPermitService
from .world_model import WorldModelService

PROTOCOL = "hae-payment-intent-capability-v1"
CAPABILITY = "prepare_payment_intent"
MAX_USES = 1
AUDIENCE_PREFIX = "payment-preparer:"


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


def _public_jwk(identity: AgentSigningIdentity) -> dict:
    return {
        "kty": "OKP",
        "crv": "Ed25519",
        "x": identity.public_key_b64,
        "kid": identity.key_id,
        "use": "sig",
        "alg": "EdDSA",
    }


class PaymentIntentCapabilityService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _validate_audience(audience: str) -> str:
        normalized = audience.strip()
        if not normalized.startswith(AUDIENCE_PREFIX):
            raise ValueError(f"payment preparation audience must start with {AUDIENCE_PREFIX}")
        suffix = normalized[len(AUDIENCE_PREFIX):].strip()
        if not suffix or suffix == "*" or "*" in suffix:
            raise ValueError("payment preparation audience must identify one exact adapter")
        return normalized

    def _current_context(self, user: User, permit: PseudonymousSettlementPermit):
        if permit.user_id != user.id:
            raise ValueError("settlement permit does not belong to user")
        if permit.status != "consumed" or permit.use_count != 1 or permit.consumed_at is None:
            raise ValueError("settlement permit must be consumed before payment-intent preparation")

        private = (
            self.db.query(CollectivePrivateAllocation)
            .filter(CollectivePrivateAllocation.id == permit.private_allocation_id)
            .one()
        )
        (
            round_row,
            offer,
            commitment,
            decision,
            envelope,
            mandate,
            receipt,
            responder_audience,
        ) = SettlementPermitService(self.db)._current_context(user, private)

        if receipt.id != permit.settlement_receipt_id:
            raise ValueError("collective settlement readiness changed after settlement permit")
        if round_row.allocation_set_hash != permit.allocation_set_hash:
            raise ValueError("allocation changed after settlement permit")
        if receipt.accepted_set_hash != permit.accepted_set_hash:
            raise ValueError("accepted collective set changed after settlement permit")
        if offer.offer_hash != permit.offer_hash:
            raise ValueError("signed offer changed after settlement permit")
        if decision.decision_hash != permit.decision_hash:
            raise ValueError("post-allocation acceptance changed after settlement permit")
        if commitment.conditions_hash != permit.conditions_hash:
            raise ValueError("private commitment conditions changed after settlement permit")
        if mandate.version != permit.mandate_version:
            raise ValueError("Personal Mandate changed after settlement permit")
        if responder_audience != permit.audience:
            raise ValueError("merchant responder changed after settlement permit")
        if not receipt.settlement_ready:
            raise ValueError("collective settlement is no longer ready")

        unit_price = round(float(offer.payload["unit_price"]), 6)
        exact_total = round(unit_price * int(private.allocated_quantity), 6)
        if decision.unit_price != unit_price or decision.currency != offer.payload["currency"]:
            raise ValueError("accepted payment terms changed after settlement permit")
        if round(float(decision.exact_total_amount), 6) != exact_total:
            raise ValueError("accepted total amount changed after settlement permit")
        return private, round_row, offer, commitment, decision, envelope, mandate, receipt

    def _terms(self, user: User, permit: PseudonymousSettlementPermit, audience: str) -> dict:
        audience = self._validate_audience(audience)
        (
            private,
            round_row,
            offer,
            commitment,
            decision,
            _envelope,
            mandate,
            receipt,
        ) = self._current_context(user, permit)
        exact_total = round(float(decision.exact_total_amount), 6)
        terms = {
            "protocol": PROTOCOL,
            "capability": CAPABILITY,
            "audience": audience,
            "parent_settlement_permit_id": permit.permit_id,
            "readiness_hash": permit.readiness_hash,
            "accepted_set_hash": receipt.accepted_set_hash,
            "allocation_set_hash": round_row.allocation_set_hash,
            "offer_hash": offer.offer_hash,
            "decision_hash": decision.decision_hash,
            "conditions_hash": commitment.conditions_hash,
            "mandate_version": mandate.version,
            "allocated_quantity": int(private.allocated_quantity),
            "unit_price": round(float(decision.unit_price), 6),
            "currency": decision.currency,
            "exact_total_amount": exact_total,
            "restrictions": {
                "debit_allowed": False,
                "capture_allowed": False,
                "funds_movement_allowed": False,
                "payment_instrument_access": False,
                "order_creation_allowed": False,
                "external_dispatch": False,
            },
        }
        terms["payment_terms_hash"] = sha256_dict(terms)
        return terms

    def preview(self, user: User, request: PaymentIntentPreview) -> dict:
        permit = (
            self.db.query(PseudonymousSettlementPermit)
            .filter(PseudonymousSettlementPermit.permit_id == request.settlement_permit_id)
            .one_or_none()
        )
        if not permit:
            raise ValueError("settlement permit not found")
        terms = self._terms(user, permit, request.audience)
        return {
            "settlement_permit_id": permit.permit_id,
            "audience": terms["audience"],
            "allocated_quantity": terms["allocated_quantity"],
            "unit_price": terms["unit_price"],
            "currency": terms["currency"],
            "exact_total_amount": terms["exact_total_amount"],
            "payment_terms_hash": terms["payment_terms_hash"],
            "confirm": (
                f"ISSUE PAYMENT INTENT {permit.permit_id} "
                f"{terms['payment_terms_hash'][-12:]}"
            ),
            "restrictions": terms["restrictions"],
            "payment_instrument_required": False,
            "payment_instrument_disclosed": False,
            "funds_moved": False,
            "payment_created": False,
            "order_created": False,
        }

    def issue(self, user: User, request: PaymentIntentIssue) -> tuple[PaymentIntentCapability, dict]:
        permit = (
            self.db.query(PseudonymousSettlementPermit)
            .filter(PseudonymousSettlementPermit.permit_id == request.settlement_permit_id)
            .one_or_none()
        )
        if not permit:
            raise ValueError("settlement permit not found")
        terms = self._terms(user, permit, request.audience)
        required = f"ISSUE PAYMENT INTENT {permit.permit_id} {terms['payment_terms_hash'][-12:]}"
        if request.confirm != required:
            raise ValueError(f"confirmation must equal: {required}")

        existing = (
            self.db.query(PaymentIntentCapability)
            .filter(PaymentIntentCapability.settlement_permit_id == permit.id)
            .one_or_none()
        )
        if existing:
            raise ValueError("a payment-intent capability was already issued for this settlement permit")

        identity = (
            self.db.query(AgentSigningIdentity)
            .filter(AgentSigningIdentity.id == permit.signing_identity_id)
            .one()
        )
        if identity.revoked_at is not None:
            raise ValueError("user signing identity is revoked")

        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=request.expires_in_seconds)
        capability_id = uuid.uuid4().hex
        subject_ref = uuid.uuid4().hex
        claims = {
            "iss": f"hae:{identity.key_id}",
            "sub": subject_ref,
            "aud": terms["audience"],
            "jti": capability_id,
            "iat": _epoch(now),
            "exp": _epoch(expires_at),
            "protocol": PROTOCOL,
            "capability": CAPABILITY,
            "payment_terms": {
                "hash": terms["payment_terms_hash"],
                "allocated_quantity": terms["allocated_quantity"],
                "unit_price": terms["unit_price"],
                "currency": terms["currency"],
                "exact_total_amount": terms["exact_total_amount"],
            },
            "context": {
                "parent_settlement_permit_id": permit.permit_id,
                "readiness_hash": terms["readiness_hash"],
                "accepted_set_hash": terms["accepted_set_hash"],
                "allocation_set_hash": terms["allocation_set_hash"],
                "offer_hash": terms["offer_hash"],
                "decision_hash": terms["decision_hash"],
                "conditions_hash": terms["conditions_hash"],
            },
            "mandate": {"version": terms["mandate_version"]},
            "restrictions": terms["restrictions"],
            "max_uses": MAX_USES,
            "nonce": secrets.token_urlsafe(24),
        }
        token = self._sign(identity, claims)
        capability = PaymentIntentCapability(
            user_id=user.id,
            settlement_permit_id=permit.id,
            signing_identity_id=identity.id,
            capability_id=capability_id,
            subject_ref=subject_ref,
            audience=terms["audience"],
            token_hash=_token_hash(token),
            payment_terms_hash=terms["payment_terms_hash"],
            readiness_hash=terms["readiness_hash"],
            allocation_set_hash=terms["allocation_set_hash"],
            accepted_set_hash=terms["accepted_set_hash"],
            offer_hash=terms["offer_hash"],
            decision_hash=terms["decision_hash"],
            conditions_hash=terms["conditions_hash"],
            mandate_version=terms["mandate_version"],
            allocated_quantity=terms["allocated_quantity"],
            unit_price=terms["unit_price"],
            currency=terms["currency"],
            exact_total_amount=terms["exact_total_amount"],
            status="active",
            use_count=0,
            issued_at=now,
            expires_at=expires_at,
        )
        self.db.add(capability)
        self.db.flush()
        WorldModelService(self.db).append_event(
            user,
            EventCreate(
                event_type="payment.intent_capability_issued",
                source="user",
                subject_type="payment_intent_capability",
                subject_id=capability.capability_id,
                payload={
                    "audience": capability.audience,
                    "payment_terms_hash": capability.payment_terms_hash,
                    "currency": capability.currency,
                    "exact_total_amount": capability.exact_total_amount,
                    "debit_allowed": False,
                    "capture_allowed": False,
                    "funds_movement_allowed": False,
                    "payment_instrument_disclosed": False,
                    "external_dispatch": False,
                    "payment_created": False,
                    "order_created": False,
                },
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(capability)
        return capability, {
            "token": token,
            "claims": claims,
            "public_jwk": _public_jwk(identity),
        }

    def verify(self, token: str, audience: str) -> dict:
        header, claims, identity = self._verify_signature(token)
        capability = (
            self.db.query(PaymentIntentCapability)
            .filter(PaymentIntentCapability.capability_id == claims.get("jti"))
            .one_or_none()
        )
        self._validate_registered(capability, identity, claims, token, audience)
        return {
            "valid": True,
            "claims": claims,
            "public_jwk": _public_jwk(identity),
            "debit_allowed": False,
            "capture_allowed": False,
            "funds_movement_allowed": False,
            "payment_instrument_access": False,
            "external_dispatch": False,
            "payment_created": False,
            "order_created": False,
        }

    def consume(self, request: PaymentIntentConsume) -> PaymentIntentCapabilityUse:
        header, claims, identity = self._verify_signature(request.token)
        capability = (
            self.db.query(PaymentIntentCapability)
            .filter(PaymentIntentCapability.capability_id == claims.get("jti"))
            .with_for_update()
            .one_or_none()
        )
        self._validate_registered(
            capability,
            identity,
            claims,
            request.token,
            request.audience,
        )
        existing = (
            self.db.query(PaymentIntentCapabilityUse)
            .filter(
                PaymentIntentCapabilityUse.capability_db_id == capability.id,
                PaymentIntentCapabilityUse.request_id == request.request_id,
            )
            .one_or_none()
        )
        if existing:
            raise ValueError("payment-intent request_id has already been consumed")
        if capability.use_count >= MAX_USES:
            raise ValueError("payment-intent capability is exhausted")

        use = PaymentIntentCapabilityUse(
            capability_db_id=capability.id,
            request_id=request.request_id,
            audience=request.audience,
        )
        self.db.add(use)
        capability.use_count = 1
        capability.status = "consumed"
        capability.consumed_at = datetime.utcnow()
        self.db.flush()
        user = self.db.query(User).filter(User.id == capability.user_id).one()
        WorldModelService(self.db).append_event(
            user,
            EventCreate(
                event_type="payment.intent_capability_consumed",
                source="payment_preparation_boundary",
                subject_type="payment_intent_capability",
                subject_id=capability.capability_id,
                payload={
                    "request_id": request.request_id,
                    "audience": request.audience,
                    "effect": "prepare_payment_intent_only",
                    "debit_allowed": False,
                    "capture_allowed": False,
                    "funds_movement_allowed": False,
                    "payment_instrument_disclosed": False,
                    "external_dispatch": False,
                    "payment_created": False,
                    "order_created": False,
                },
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(use)
        return use

    def revoke(self, user: User, capability: PaymentIntentCapability, confirm: str):
        if capability.user_id != user.id:
            raise ValueError("payment-intent capability does not belong to user")
        required = f"REVOKE PAYMENT INTENT {capability.capability_id}"
        if confirm != required:
            raise ValueError(f"confirmation must equal: {required}")
        if capability.status == "consumed":
            raise ValueError("consumed payment-intent capability cannot be revoked retroactively")
        if capability.revoked_at is None:
            capability.status = "revoked"
            capability.revoked_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(capability)
        return capability

    def _validate_registered(
        self,
        capability: PaymentIntentCapability | None,
        identity: AgentSigningIdentity,
        claims: dict,
        token: str,
        audience: str,
    ) -> None:
        if not capability:
            raise ValueError("payment-intent capability is not registered")
        if not hmac.compare_digest(capability.token_hash, _token_hash(token)):
            raise ValueError("payment-intent bearer token does not match registry")
        if capability.signing_identity_id != identity.id or identity.revoked_at is not None:
            raise ValueError("payment-intent signing identity is invalid")
        if capability.status != "active" or capability.revoked_at is not None:
            raise ValueError("payment-intent capability is not active")
        now = datetime.utcnow()
        if capability.expires_at <= now or int(claims.get("exp", 0)) <= _epoch(now):
            raise ValueError("payment-intent capability is expired")
        if capability.use_count >= MAX_USES:
            raise ValueError("payment-intent capability is exhausted")
        if audience != capability.audience or claims.get("aud") != capability.audience:
            raise ValueError("payment-intent audience mismatch")
        if claims.get("protocol") != PROTOCOL or claims.get("capability") != CAPABILITY:
            raise ValueError("unsupported payment-intent protocol or capability")
        if claims.get("jti") != capability.capability_id or claims.get("sub") != capability.subject_ref:
            raise ValueError("payment-intent identifiers do not match registry")
        if int(claims.get("max_uses", 0)) != MAX_USES:
            raise ValueError("payment-intent max_uses mismatch")

        restrictions = claims.get("restrictions", {})
        required_false = {
            "debit_allowed",
            "capture_allowed",
            "funds_movement_allowed",
            "payment_instrument_access",
            "order_creation_allowed",
            "external_dispatch",
        }
        if any(restrictions.get(key) is not False for key in required_false):
            raise ValueError("payment-intent proof attempts to grant forbidden authority")

        payment_terms = claims.get("payment_terms", {})
        if payment_terms.get("hash") != capability.payment_terms_hash:
            raise ValueError("payment-intent terms hash mismatch")
        if int(payment_terms.get("allocated_quantity", -1)) != capability.allocated_quantity:
            raise ValueError("payment-intent quantity mismatch")
        if payment_terms.get("currency") != capability.currency:
            raise ValueError("payment-intent currency mismatch")
        if round(float(payment_terms.get("unit_price", -1)), 6) != round(capability.unit_price, 6):
            raise ValueError("payment-intent unit price mismatch")
        if round(float(payment_terms.get("exact_total_amount", -1)), 6) != round(capability.exact_total_amount, 6):
            raise ValueError("payment-intent total amount mismatch")

        context = claims.get("context", {})
        if context.get("readiness_hash") != capability.readiness_hash:
            raise ValueError("payment-intent readiness hash mismatch")
        if context.get("accepted_set_hash") != capability.accepted_set_hash:
            raise ValueError("payment-intent accepted-set hash mismatch")
        if context.get("allocation_set_hash") != capability.allocation_set_hash:
            raise ValueError("payment-intent allocation hash mismatch")
        if context.get("offer_hash") != capability.offer_hash:
            raise ValueError("payment-intent offer hash mismatch")
        if context.get("decision_hash") != capability.decision_hash:
            raise ValueError("payment-intent decision hash mismatch")
        if context.get("conditions_hash") != capability.conditions_hash:
            raise ValueError("payment-intent conditions hash mismatch")
        if int(claims.get("mandate", {}).get("version", 0)) != capability.mandate_version:
            raise ValueError("payment-intent mandate version mismatch")

        permit = (
            self.db.query(PseudonymousSettlementPermit)
            .filter(PseudonymousSettlementPermit.id == capability.settlement_permit_id)
            .one()
        )
        user = self.db.query(User).filter(User.id == capability.user_id).one()
        current_terms = self._terms(user, permit, capability.audience)
        if current_terms["payment_terms_hash"] != capability.payment_terms_hash:
            raise ValueError("payment-intent terms changed after issuance")
        if current_terms["mandate_version"] != capability.mandate_version:
            raise ValueError("Personal Mandate changed after payment-intent issuance")

    def _sign(self, identity: AgentSigningIdentity, claims: dict) -> str:
        cipher = TokenCipher()
        private_raw = _b64u_decode(cipher.decrypt(identity.encrypted_private_key))
        private_key = Ed25519PrivateKey.from_private_bytes(private_raw)
        header = {"alg": "EdDSA", "typ": "HAE-PAYMENT-INTENT", "kid": identity.key_id}
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
            if header.get("alg") != "EdDSA" or header.get("typ") != "HAE-PAYMENT-INTENT":
                raise ValueError("unexpected payment-intent header")
            identity = (
                self.db.query(AgentSigningIdentity)
                .filter(AgentSigningIdentity.key_id == header.get("kid"))
                .one_or_none()
            )
            if not identity:
                raise ValueError("unknown payment-intent signing key")
            public_key = Ed25519PublicKey.from_public_bytes(_b64u_decode(identity.public_key_b64))
            public_key.verify(
                _b64u_decode(encoded_signature),
                f"{encoded_header}.{encoded_claims}".encode("ascii"),
            )
        except (ValueError, InvalidSignature, json.JSONDecodeError, TypeError) as exc:
            raise ValueError("invalid payment-intent capability signature") from exc
        return header, claims, identity
