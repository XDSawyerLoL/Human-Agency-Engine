from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from sqlalchemy.orm import Session

from ..acceptance_models import CollectiveAllocationDecision
from ..allocation_models import CollectiveAllocationRound, CollectivePrivateAllocation
from ..collective_offer_models import CollectiveMarketOffer
from ..delegation_models import AgentSigningIdentity
from ..market_models import PrivateIntentEnvelope
from ..models import PersonalMandate, User
from ..quorum_models import CollectiveConditionalCommitment
from ..settlement_models import CollectiveSettlementReadinessReceipt
from ..settlement_permit_models import PseudonymousSettlementPermit, SettlementPermitUse
from ..settlement_permit_schemas import SettlementPermitConsume, SettlementPermitIssue
from ..world_schemas import EventCreate
from .crypto import TokenCipher
from .delegation import DelegationService
from .policy import canonical_json, sha256_dict
from .settlement import CollectiveSettlementService
from .world_model import WorldModelService

PROTOCOL = "hae-pseudonymous-settlement-permit-v1"
CAPABILITY = "prepare_settlement"
MAX_USES = 1


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


def _readiness_hash(receipt: CollectiveSettlementReadinessReceipt) -> str:
    return sha256_dict(
        {
            "receipt_id": receipt.receipt_id,
            "allocation_set_hash": receipt.allocation_set_hash,
            "commitment_set_hash": receipt.commitment_set_hash,
            "accepted_set_hash": receipt.accepted_set_hash,
            "accepted_user_count": receipt.accepted_user_count,
            "accepted_quantity": receipt.accepted_quantity,
            "allocated_user_count": receipt.allocated_user_count,
            "allocated_quantity": receipt.allocated_quantity,
            "unit_price": receipt.unit_price,
            "currency": receipt.currency,
            "exact_total_amount": receipt.exact_total_amount,
            "minimum_anonymity_set": receipt.minimum_anonymity_set,
            "all_allocated_users_accepted": receipt.all_allocated_users_accepted,
            "commercial_minimum_met": receipt.commercial_minimum_met,
            "capacity_ok": receipt.capacity_ok,
            "settlement_ready": receipt.settlement_ready,
        }
    )


class SettlementPermitService:
    def __init__(self, db: Session):
        self.db = db

    def _current_context(self, user: User, private: CollectivePrivateAllocation):
        if private.user_id != user.id:
            raise ValueError("private allocation does not belong to user")
        if private.allocated_quantity <= 0 or private.status != "allocated":
            raise ValueError("settlement permit requires a positive private allocation")

        round_row = (
            self.db.query(CollectiveAllocationRound)
            .filter(CollectiveAllocationRound.id == private.allocation_round_id)
            .one()
        )
        offer = (
            self.db.query(CollectiveMarketOffer)
            .filter(CollectiveMarketOffer.id == round_row.offer_db_id)
            .one()
        )
        commitment = (
            self.db.query(CollectiveConditionalCommitment)
            .filter(CollectiveConditionalCommitment.id == private.commitment_id)
            .one()
        )
        decision = (
            self.db.query(CollectiveAllocationDecision)
            .filter(CollectiveAllocationDecision.private_allocation_id == private.id)
            .one_or_none()
        )
        if not decision or decision.decision != "accepted" or decision.revoked_at is not None:
            raise ValueError("effective post-allocation acceptance is required")
        if commitment.status != "active":
            raise ValueError("conditional commitment is no longer active")
        if decision.allocation_set_hash != round_row.allocation_set_hash:
            raise ValueError("acceptance no longer matches allocation round")
        if decision.offer_hash != offer.offer_hash:
            raise ValueError("acceptance no longer matches signed collective offer")
        if decision.conditions_hash != commitment.conditions_hash:
            raise ValueError("acceptance no longer matches private commitment conditions")
        if decision.allocated_quantity != private.allocated_quantity:
            raise ValueError("acceptance quantity no longer matches private allocation")

        envelope = (
            self.db.query(PrivateIntentEnvelope)
            .filter(PrivateIntentEnvelope.id == commitment.membership.envelope_db_id)
            .one_or_none()
            if hasattr(commitment, "membership") and commitment.membership is not None
            else None
        )
        if envelope is None:
            # Avoid relying on an ORM relationship: resolve through the membership id explicitly.
            from ..collective_models import CollectiveIntentMembership

            membership = (
                self.db.query(CollectiveIntentMembership)
                .filter(CollectiveIntentMembership.id == commitment.membership_id)
                .one()
            )
            envelope = (
                self.db.query(PrivateIntentEnvelope)
                .filter(PrivateIntentEnvelope.id == membership.envelope_db_id)
                .one()
            )
        if commitment.envelope_hash != envelope.envelope_hash:
            raise ValueError("private intent changed after commitment")

        mandate = (
            self.db.query(PersonalMandate)
            .filter(PersonalMandate.user_id == user.id)
            .one_or_none()
        )
        if not mandate or mandate.version != envelope.mandate_version:
            raise ValueError("Personal Mandate changed after private market intent")

        settlement = CollectiveSettlementService(self.db)
        receipt = settlement.effective_receipt(offer)
        if receipt is None:
            receipt = settlement.assess(offer)
        if not receipt.settlement_ready:
            raise ValueError("collective settlement is not currently ready")
        effective = settlement.effective_receipt(offer)
        if not effective or effective.id != receipt.id:
            raise ValueError("collective settlement readiness is not current")
        if receipt.allocation_set_hash != round_row.allocation_set_hash:
            raise ValueError("settlement readiness no longer matches allocation")
        if receipt.accepted_set_hash == "":
            raise ValueError("settlement readiness accepted-set hash is missing")

        unit_price = round(float(offer.payload["unit_price"]), 6)
        exact_total_amount = round(unit_price * int(private.allocated_quantity), 6)
        if decision.unit_price != unit_price or decision.currency != offer.payload["currency"]:
            raise ValueError("accepted commercial terms changed after acceptance")
        if round(float(decision.exact_total_amount), 6) != exact_total_amount:
            raise ValueError("accepted total amount changed after acceptance")

        audience = f"responder:{offer.responder_id}"
        return round_row, offer, commitment, decision, envelope, mandate, receipt, audience

    def issue(self, user: User, request: SettlementPermitIssue) -> tuple[PseudonymousSettlementPermit, dict]:
        private = (
            self.db.query(CollectivePrivateAllocation)
            .filter(CollectivePrivateAllocation.allocation_entry_id == request.allocation_entry_id)
            .one_or_none()
        )
        if not private:
            raise ValueError("private allocation not found")
        (
            round_row,
            offer,
            commitment,
            decision,
            _envelope,
            mandate,
            receipt,
            audience,
        ) = self._current_context(user, private)

        required = (
            f"ISSUE SETTLEMENT PERMIT {private.allocation_entry_id} "
            f"{decision.decision_hash[-12:]}"
        )
        if request.confirm != required:
            raise ValueError(f"confirmation must equal: {required}")

        previous = (
            self.db.query(PseudonymousSettlementPermit)
            .filter(PseudonymousSettlementPermit.decision_id == decision.id)
            .first()
        )
        if previous:
            raise ValueError("a settlement permit was already issued for this exact acceptance")

        identity = DelegationService(self.db).ensure_identity(user)
        if identity.revoked_at is not None:
            raise ValueError("user signing identity is revoked")
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=request.expires_in_seconds)
        permit_id = uuid.uuid4().hex
        subject_ref = uuid.uuid4().hex
        readiness_hash = _readiness_hash(receipt)
        claims = {
            "iss": f"hae:{identity.key_id}",
            "sub": subject_ref,
            "aud": audience,
            "jti": permit_id,
            "iat": _epoch(now),
            "exp": _epoch(expires_at),
            "protocol": PROTOCOL,
            "capability": CAPABILITY,
            "readiness": {
                "hash": readiness_hash,
                "accepted_set_hash": receipt.accepted_set_hash,
            },
            "offer": {
                "hash": offer.offer_hash,
                "responder_id": offer.responder_id,
            },
            "allocation": {
                "set_hash": round_row.allocation_set_hash,
                "quantity": private.allocated_quantity,
            },
            "acceptance": {
                "decision_hash": decision.decision_hash,
                "conditions_hash": commitment.conditions_hash,
            },
            "terms": {
                "unit_price": round(float(decision.unit_price), 6),
                "currency": decision.currency,
                "exact_total_amount": round(float(decision.exact_total_amount), 6),
            },
            "mandate": {"version": mandate.version},
            "max_uses": MAX_USES,
            "nonce": secrets.token_urlsafe(24),
        }
        token = self._sign(identity, claims)
        permit = PseudonymousSettlementPermit(
            user_id=user.id,
            settlement_receipt_id=receipt.id,
            private_allocation_id=private.id,
            decision_id=decision.id,
            signing_identity_id=identity.id,
            permit_id=permit_id,
            subject_ref=subject_ref,
            audience=audience,
            token_hash=_token_hash(token),
            readiness_hash=readiness_hash,
            allocation_set_hash=round_row.allocation_set_hash,
            accepted_set_hash=receipt.accepted_set_hash,
            offer_hash=offer.offer_hash,
            decision_hash=decision.decision_hash,
            conditions_hash=commitment.conditions_hash,
            mandate_version=mandate.version,
            allocated_quantity=private.allocated_quantity,
            unit_price=round(float(decision.unit_price), 6),
            currency=decision.currency,
            exact_total_amount=round(float(decision.exact_total_amount), 6),
            status="active",
            use_count=0,
            issued_at=now,
            expires_at=expires_at,
        )
        self.db.add(permit)
        self.db.flush()
        WorldModelService(self.db).append_event(
            user,
            EventCreate(
                event_type="collective.settlement_permit_issued",
                source="user",
                subject_type="pseudonymous_settlement_permit",
                subject_id=permit.permit_id,
                payload={
                    "audience": permit.audience,
                    "readiness_hash": permit.readiness_hash,
                    "allocation_set_hash": permit.allocation_set_hash,
                    "offer_hash": permit.offer_hash,
                    "allocated_quantity": permit.allocated_quantity,
                    "currency": permit.currency,
                    "exact_total_amount": permit.exact_total_amount,
                    "identity_disclosed": False,
                    "address_disclosed": False,
                    "payment_instrument_disclosed": False,
                    "external_dispatch": False,
                    "payment_created": False,
                    "order_created": False,
                },
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(permit)
        return permit, {
            "token": token,
            "claims": claims,
            "public_jwk": _public_jwk(identity),
        }

    def verify(self, token: str, audience: str) -> dict:
        header, claims, identity = self._verify_signature(token)
        permit = (
            self.db.query(PseudonymousSettlementPermit)
            .filter(PseudonymousSettlementPermit.permit_id == claims.get("jti"))
            .one_or_none()
        )
        self._validate_registered(permit, identity, claims, token, audience)
        return {
            "valid": True,
            "header": header,
            "claims": claims,
            "public_jwk": _public_jwk(identity),
            "identity_disclosed": False,
            "address_disclosed": False,
            "payment_instrument_disclosed": False,
            "external_dispatch": False,
            "payment_created": False,
            "order_created": False,
        }

    def consume(self, request: SettlementPermitConsume) -> SettlementPermitUse:
        header, claims, identity = self._verify_signature(request.token)
        permit = (
            self.db.query(PseudonymousSettlementPermit)
            .filter(PseudonymousSettlementPermit.permit_id == claims.get("jti"))
            .with_for_update()
            .one_or_none()
        )
        self._validate_registered(permit, identity, claims, request.token, request.audience)
        existing = (
            self.db.query(SettlementPermitUse)
            .filter(
                SettlementPermitUse.permit_db_id == permit.id,
                SettlementPermitUse.request_id == request.request_id,
            )
            .one_or_none()
        )
        if existing:
            raise ValueError("settlement permit request_id has already been consumed")
        if permit.use_count >= MAX_USES:
            raise ValueError("settlement permit is exhausted")

        use = SettlementPermitUse(
            permit_db_id=permit.id,
            request_id=request.request_id,
            audience=request.audience,
        )
        self.db.add(use)
        permit.use_count = 1
        permit.status = "consumed"
        permit.consumed_at = datetime.utcnow()
        self.db.flush()
        user = self.db.query(User).filter(User.id == permit.user_id).one()
        WorldModelService(self.db).append_event(
            user,
            EventCreate(
                event_type="collective.settlement_permit_consumed",
                source="settlement_permit_verifier",
                subject_type="pseudonymous_settlement_permit",
                subject_id=permit.permit_id,
                payload={
                    "request_id": request.request_id,
                    "audience": request.audience,
                    "effect": "prepare_settlement_only",
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

    def revoke(self, user: User, permit: PseudonymousSettlementPermit, confirm: str):
        if permit.user_id != user.id:
            raise ValueError("settlement permit does not belong to user")
        required = f"REVOKE SETTLEMENT PERMIT {permit.permit_id}"
        if confirm != required:
            raise ValueError(f"confirmation must equal: {required}")
        if permit.status == "consumed":
            raise ValueError("consumed settlement permit cannot be revoked retroactively")
        if permit.revoked_at is None:
            permit.status = "revoked"
            permit.revoked_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(permit)
        return permit

    def _validate_registered(
        self,
        permit: PseudonymousSettlementPermit | None,
        identity: AgentSigningIdentity,
        claims: dict,
        token: str,
        audience: str,
    ) -> None:
        if not permit:
            raise ValueError("settlement permit is not registered")
        if not hmac.compare_digest(permit.token_hash, _token_hash(token)):
            raise ValueError("settlement permit token does not match registered proof")
        if permit.signing_identity_id != identity.id or identity.revoked_at is not None:
            raise ValueError("settlement permit signing identity is invalid")
        if permit.status != "active" or permit.revoked_at is not None:
            raise ValueError("settlement permit is not active")
        now = datetime.utcnow()
        if permit.expires_at <= now or int(claims.get("exp", 0)) <= _epoch(now):
            raise ValueError("settlement permit is expired")
        if permit.use_count >= MAX_USES:
            raise ValueError("settlement permit is exhausted")
        if audience != permit.audience or claims.get("aud") != permit.audience:
            raise ValueError("settlement permit audience mismatch")
        if claims.get("protocol") != PROTOCOL or claims.get("capability") != CAPABILITY:
            raise ValueError("unsupported settlement permit protocol or capability")
        if claims.get("jti") != permit.permit_id or claims.get("sub") != permit.subject_ref:
            raise ValueError("settlement permit identifiers do not match registry")
        if int(claims.get("max_uses", 0)) != MAX_USES:
            raise ValueError("settlement permit max_uses mismatch")
        if claims.get("readiness", {}).get("hash") != permit.readiness_hash:
            raise ValueError("settlement readiness hash mismatch")
        if claims.get("readiness", {}).get("accepted_set_hash") != permit.accepted_set_hash:
            raise ValueError("settlement accepted-set hash mismatch")
        if claims.get("offer", {}).get("hash") != permit.offer_hash:
            raise ValueError("settlement offer hash mismatch")
        if claims.get("allocation", {}).get("set_hash") != permit.allocation_set_hash:
            raise ValueError("settlement allocation hash mismatch")
        if int(claims.get("allocation", {}).get("quantity", -1)) != permit.allocated_quantity:
            raise ValueError("settlement allocated quantity mismatch")
        if claims.get("acceptance", {}).get("decision_hash") != permit.decision_hash:
            raise ValueError("settlement decision hash mismatch")
        if claims.get("acceptance", {}).get("conditions_hash") != permit.conditions_hash:
            raise ValueError("settlement conditions hash mismatch")
        if int(claims.get("mandate", {}).get("version", 0)) != permit.mandate_version:
            raise ValueError("settlement mandate version mismatch")
        if claims.get("terms", {}).get("currency") != permit.currency:
            raise ValueError("settlement currency mismatch")
        if round(float(claims.get("terms", {}).get("unit_price", -1)), 6) != round(permit.unit_price, 6):
            raise ValueError("settlement unit price mismatch")
        if round(float(claims.get("terms", {}).get("exact_total_amount", -1)), 6) != round(permit.exact_total_amount, 6):
            raise ValueError("settlement total amount mismatch")

        user = self.db.query(User).filter(User.id == permit.user_id).one()
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
            _envelope,
            mandate,
            receipt,
            current_audience,
        ) = self._current_context(user, private)
        if receipt.id != permit.settlement_receipt_id or _readiness_hash(receipt) != permit.readiness_hash:
            raise ValueError("settlement readiness changed after permit issuance")
        if round_row.allocation_set_hash != permit.allocation_set_hash:
            raise ValueError("settlement allocation changed after permit issuance")
        if offer.offer_hash != permit.offer_hash or current_audience != permit.audience:
            raise ValueError("settlement offer or responder changed after permit issuance")
        if decision.decision_hash != permit.decision_hash or commitment.conditions_hash != permit.conditions_hash:
            raise ValueError("settlement acceptance changed after permit issuance")
        if mandate.version != permit.mandate_version:
            raise ValueError("Personal Mandate changed after permit issuance")

    def _sign(self, identity: AgentSigningIdentity, claims: dict) -> str:
        cipher = TokenCipher()
        private_raw = _b64u_decode(cipher.decrypt(identity.encrypted_private_key))
        private_key = Ed25519PrivateKey.from_private_bytes(private_raw)
        header = {
            "alg": "EdDSA",
            "typ": "HAE-SETTLEMENT-PERMIT",
            "kid": identity.key_id,
        }
        encoded_header = _b64u(canonical_json(header))
        encoded_claims = _b64u(canonical_json(claims))
        signing_input = f"{encoded_header}.{encoded_claims}".encode("ascii")
        signature = private_key.sign(signing_input)
        return f"{encoded_header}.{encoded_claims}.{_b64u(signature)}"

    def _verify_signature(self, token: str) -> tuple[dict, dict, AgentSigningIdentity]:
        try:
            encoded_header, encoded_claims, encoded_signature = token.split(".")
            header = json.loads(_b64u_decode(encoded_header))
            claims = json.loads(_b64u_decode(encoded_claims))
            if header.get("alg") != "EdDSA" or header.get("typ") != "HAE-SETTLEMENT-PERMIT":
                raise ValueError("unexpected settlement permit header")
            identity = (
                self.db.query(AgentSigningIdentity)
                .filter(AgentSigningIdentity.key_id == header.get("kid"))
                .one_or_none()
            )
            if not identity:
                raise ValueError("unknown settlement permit signing key")
            public_key = Ed25519PublicKey.from_public_bytes(_b64u_decode(identity.public_key_b64))
            public_key.verify(
                _b64u_decode(encoded_signature),
                f"{encoded_header}.{encoded_claims}".encode("ascii"),
            )
        except (ValueError, InvalidSignature, json.JSONDecodeError, TypeError) as exc:
            raise ValueError("invalid settlement permit signature") from exc
        return header, claims, identity
