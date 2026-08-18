from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy.orm import Session

from ..acquisition_models import InformationNeed
from ..market_models import MarketOffer, PrivateIntentEnvelope
from ..market_schemas import MarketOfferSubmit, PrivateIntentOpen
from ..models import PersonalMandate, User
from ..synthesis_models import CandidateIntervention
from ..world_schemas import EventCreate
from .policy import action_fingerprint, canonical_json, sha256_dict
from .world_model import WorldModelService

MARKET_PROTOCOL = "hae-private-intent-market-v1"
MAX_FEATURE_LENGTH = 80
MAX_LABEL_LENGTH = 255


def _b64u_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _key_fingerprint(public_raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(public_raw).hexdigest()


def _epoch(value: datetime) -> int:
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return int(aware.timestamp())


def _clean_feature(value: str) -> str:
    cleaned = " ".join(value.strip().lower().split())
    if not cleaned or len(cleaned) > MAX_FEATURE_LENGTH:
        raise ValueError(f"features must contain 1-{MAX_FEATURE_LENGTH} visible characters")
    return cleaned


def _normalize_disclosure(request: PrivateIntentOpen) -> dict:
    data = request.disclosure.model_dump()
    data["category"] = " ".join(data["category"].strip().lower().split())
    data["currency"] = data["currency"].upper()
    data["country"] = data["country"].upper()
    if not data["category"]:
        raise ValueError("category cannot be empty")
    if not data["currency"].isalpha():
        raise ValueError("currency must be a three-letter alphabetic code")
    if not data["country"].isalpha():
        raise ValueError("country must be a two-letter alphabetic code")
    if data.get("size") is not None:
        data["size"] = " ".join(data["size"].strip().split())
        if not data["size"]:
            data["size"] = None
    data["required_features"] = sorted({_clean_feature(item) for item in data["required_features"]})
    return data


def _normalize_ranking_policy(request: PrivateIntentOpen) -> dict:
    data = request.ranking_policy.model_dump()
    total = sum(float(value) for value in data.values())
    if total <= 0:
        raise ValueError("at least one fiduciary ranking weight must be positive")
    return {key: round(float(value) / total, 8) for key, value in data.items()}


def _envelope_core_payload(
    *,
    envelope_id: str,
    subject_ref: str,
    request_type: str,
    disclosure: dict,
    ranking_policy: dict,
    mandate_version: int,
    candidate_fingerprint: str,
    challenge_nonce: str,
    expires_at: datetime,
) -> dict:
    return {
        "protocol": MARKET_PROTOCOL,
        "envelope_id": envelope_id,
        "subject_ref": subject_ref,
        "request_type": request_type,
        "disclosure": disclosure,
        "ranking_policy": ranking_policy,
        "mandate": {"version": mandate_version},
        "candidate": {"fingerprint": candidate_fingerprint},
        "challenge_nonce": challenge_nonce,
        "expires_at": _epoch(expires_at),
    }


def public_envelope(envelope: PrivateIntentEnvelope) -> dict:
    return {
        "protocol": MARKET_PROTOCOL,
        "envelope_id": envelope.envelope_id,
        "subject_ref": envelope.subject_ref,
        "request_type": envelope.request_type,
        "disclosure": envelope.disclosure,
        "ranking_policy": envelope.ranking_policy,
        "candidate": {"fingerprint": envelope.candidate_fingerprint},
        "challenge_nonce": envelope.challenge_nonce,
        "envelope_hash": envelope.envelope_hash,
        "expires_at": _epoch(envelope.expires_at),
        "status": envelope.status,
        "privacy": {
            "self_graph_included": False,
            "raw_intent_included": False,
            "identity_included": False,
            "exact_address_included": False,
            "income_included": False,
            "emotional_state_included": False,
        },
    }


def _normalized_offer_data(request: MarketOfferSubmit) -> tuple[dict, bytes, str]:
    try:
        public_raw = _b64u_decode(request.public_key_b64)
        if len(public_raw) != 32:
            raise ValueError("responder Ed25519 public key must be 32 bytes")
        Ed25519PublicKey.from_public_bytes(public_raw)
    except Exception as exc:
        if isinstance(exc, ValueError) and "32 bytes" in str(exc):
            raise
        raise ValueError("invalid responder Ed25519 public key") from exc

    features = sorted({_clean_feature(item) for item in request.features})
    currency = request.currency.upper()
    if not currency.isalpha():
        raise ValueError("offer currency must be alphabetic")
    commission_currency = request.commission_currency.upper() if request.commission_currency else currency
    if request.commission_amount > 0 and commission_currency != currency:
        raise ValueError("V1 commission currency must match offer currency")
    responder_label = " ".join(request.responder_label.strip().split())[:MAX_LABEL_LENGTH]
    responder_id = _key_fingerprint(public_raw)
    data = {
        "offer_id": request.offer_id,
        "responder_label": responder_label,
        "price_total": round(float(request.price_total), 6),
        "currency": currency,
        "delivery_days": request.delivery_days,
        "return_window_days": request.return_window_days,
        "cancellation_allowed": request.cancellation_allowed,
        "available": request.available,
        "quantity_available": request.quantity_available,
        "features": features,
        "condition": request.condition,
        "commission": {
            "amount": round(float(request.commission_amount), 6),
            "currency": commission_currency,
        },
    }
    return data, public_raw, responder_id


def market_offer_signed_payload(
    envelope: PrivateIntentEnvelope,
    request: MarketOfferSubmit,
) -> dict:
    offer_data, _public_raw, responder_id = _normalized_offer_data(request)
    return {
        "protocol": MARKET_PROTOCOL,
        "envelope": {
            "envelope_id": envelope.envelope_id,
            "envelope_hash": envelope.envelope_hash,
            "challenge_nonce": envelope.challenge_nonce,
        },
        "responder": {
            "responder_id": responder_id,
            "public_key_b64": request.public_key_b64,
        },
        "offer": offer_data,
    }


class PrivateIntentMarketService:
    def __init__(self, db: Session):
        self.db = db

    def open(self, user: User, request: PrivateIntentOpen) -> PrivateIntentEnvelope:
        required = f"OPEN MARKET INTENT {request.candidate_id}"
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
            raise ValueError("market intent requires a candidate that already passed CARE + FUTURE + Decision Lab")
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
            raise ValueError("Personal Mandate must be configured before opening market intent")

        disclosure = _normalize_disclosure(request)
        ranking_policy = _normalize_ranking_policy(request)
        envelope_id = uuid.uuid4().hex
        subject_ref = uuid.uuid4().hex
        challenge_nonce = secrets.token_urlsafe(24)
        expires_at = datetime.utcnow() + timedelta(seconds=request.expires_in_seconds)
        candidate_fingerprint = action_fingerprint(candidate)
        core = _envelope_core_payload(
            envelope_id=envelope_id,
            subject_ref=subject_ref,
            request_type=request.request_type,
            disclosure=disclosure,
            ranking_policy=ranking_policy,
            mandate_version=mandate.version,
            candidate_fingerprint=candidate_fingerprint,
            challenge_nonce=challenge_nonce,
            expires_at=expires_at,
        )
        envelope = PrivateIntentEnvelope(
            user_id=user.id,
            candidate_id=candidate.id,
            envelope_id=envelope_id,
            subject_ref=subject_ref,
            request_type=request.request_type,
            category=disclosure["category"],
            disclosure=disclosure,
            ranking_policy=ranking_policy,
            mandate_version=mandate.version,
            candidate_fingerprint=candidate_fingerprint,
            challenge_nonce=challenge_nonce,
            envelope_hash=sha256_dict(core),
            status="open",
            expires_at=expires_at,
        )
        self.db.add(envelope)
        self.db.flush()
        WorldModelService(self.db).append_event(
            user,
            EventCreate(
                event_type="market.private_intent_opened",
                source="user",
                subject_type="private_intent_envelope",
                subject_id=envelope.envelope_id,
                payload={
                    "request_type": envelope.request_type,
                    "category": envelope.category,
                    "envelope_hash": envelope.envelope_hash,
                    "expires_at": envelope.expires_at.isoformat(),
                    "raw_self_disclosed": False,
                },
                correlation_id=f"candidate:{candidate.id}",
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(envelope)
        return envelope

    def revoke(self, user: User, envelope: PrivateIntentEnvelope, confirm: str) -> PrivateIntentEnvelope:
        if envelope.user_id != user.id:
            raise ValueError("market intent does not belong to user")
        required = f"REVOKE MARKET INTENT {envelope.envelope_id}"
        if confirm != required:
            raise ValueError(f"confirmation must equal: {required}")
        if envelope.status == "open":
            envelope.status = "revoked"
            envelope.revoked_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(envelope)
        return envelope

    def _validate_live_envelope(self, envelope: PrivateIntentEnvelope) -> None:
        if envelope.status != "open":
            raise ValueError("market intent is not open")
        if envelope.expires_at <= datetime.utcnow():
            envelope.status = "expired"
            self.db.commit()
            raise ValueError("market intent is expired")
        mandate = (
            self.db.query(PersonalMandate)
            .filter(PersonalMandate.user_id == envelope.user_id)
            .one_or_none()
        )
        if not mandate or mandate.version != envelope.mandate_version:
            envelope.status = "stale"
            self.db.commit()
            raise ValueError("market intent is stale because Personal Mandate changed")
        candidate = (
            self.db.query(CandidateIntervention)
            .filter(CandidateIntervention.id == envelope.candidate_id)
            .one_or_none()
        )
        if not candidate or action_fingerprint(candidate) != envelope.candidate_fingerprint:
            envelope.status = "stale"
            self.db.commit()
            raise ValueError("market intent is stale because candidate action changed")

    def submit_offer(self, envelope: PrivateIntentEnvelope, request: MarketOfferSubmit) -> MarketOffer:
        self._validate_live_envelope(envelope)
        signed_payload = market_offer_signed_payload(envelope, request)
        offer_data = signed_payload["offer"]
        responder_id = signed_payload["responder"]["responder_id"]
        public_raw = _b64u_decode(request.public_key_b64)
        try:
            signature = _b64u_decode(request.signature_b64)
            Ed25519PublicKey.from_public_bytes(public_raw).verify(signature, canonical_json(signed_payload))
        except (InvalidSignature, ValueError, TypeError) as exc:
            raise ValueError("invalid signed market offer") from exc

        offer_hash = sha256_dict(signed_payload)
        existing = self.db.query(MarketOffer).filter(MarketOffer.offer_id == request.offer_id).one_or_none()
        if existing:
            if existing.offer_hash != offer_hash:
                raise ValueError("offer_id replayed with different signed payload")
            return existing

        eligibility = self._eligibility(envelope, offer_data)
        offer = MarketOffer(
            envelope_db_id=envelope.id,
            offer_id=request.offer_id,
            responder_id=responder_id,
            responder_label=offer_data["responder_label"],
            public_key_b64=request.public_key_b64,
            signature_b64=request.signature_b64,
            offer_hash=offer_hash,
            payload=offer_data,
            eligibility=eligibility,
            status="eligible" if eligibility["eligible"] else "ineligible",
        )
        self.db.add(offer)
        self.db.flush()
        user = self.db.query(User).filter(User.id == envelope.user_id).one()
        WorldModelService(self.db).append_event(
            user,
            EventCreate(
                event_type="market.signed_offer_received",
                source="market_responder",
                subject_type="market_offer",
                subject_id=offer.offer_id,
                payload={
                    "envelope_id": envelope.envelope_id,
                    "offer_hash": offer.offer_hash,
                    "responder_id": offer.responder_id,
                    "eligible": eligibility["eligible"],
                    "identity_assurance": "key_possession_only",
                },
                correlation_id=f"candidate:{envelope.candidate_id}",
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(offer)
        return offer

    def _eligibility(self, envelope: PrivateIntentEnvelope, offer_data: dict) -> dict:
        disclosure = envelope.disclosure
        reasons: list[str] = []
        if not offer_data["available"]:
            reasons.append("not available")
        if offer_data["currency"] != disclosure["currency"]:
            reasons.append("currency mismatch")
        if offer_data["price_total"] > disclosure["budget_max"]:
            reasons.append("price exceeds budget ceiling")
        if offer_data["quantity_available"] < disclosure["quantity"]:
            reasons.append("insufficient quantity")
        condition = disclosure.get("condition", "any")
        if condition != "any" and offer_data["condition"] not in {condition, "not_applicable"}:
            reasons.append("condition mismatch")
        requested_features = set(disclosure.get("required_features") or [])
        offered_features = set(offer_data.get("features") or [])
        missing = sorted(requested_features - offered_features)
        if missing:
            reasons.append("missing seller-asserted features: " + ", ".join(missing))
        return {
            "eligible": not reasons,
            "reasons": reasons,
            "seller_feature_claims_verified": False,
            "commission_considered": False,
        }

    def rank(self, envelope: PrivateIntentEnvelope) -> dict:
        self._validate_live_envelope(envelope)
        offers = (
            self.db.query(MarketOffer)
            .filter(MarketOffer.envelope_db_id == envelope.id)
            .all()
        )
        ranked = []
        for offer in offers:
            item = self._rank_offer(envelope, offer)
            ranked.append(item)
        ranked.sort(
            key=lambda item: (
                0 if item["eligible"] else 1,
                -(item["fiduciary_score"] if item["fiduciary_score"] is not None else -1),
                item["price_total"],
                item["delivery_days"],
                item["offer_id"],
            )
        )
        return {
            "envelope_id": envelope.envelope_id,
            "ranking_policy": envelope.ranking_policy,
            "score_formula_version": "hae-fiduciary-ranking-v1",
            "commission_excluded_from_ranking": True,
            "responder_identity_assurance": "key_possession_only",
            "seller_claims_unverified": True,
            "offers": ranked,
        }

    def _rank_offer(self, envelope: PrivateIntentEnvelope, offer: MarketOffer) -> dict:
        payload = offer.payload
        eligible = bool(offer.eligibility.get("eligible"))
        if eligible:
            budget = float(envelope.disclosure["budget_max"])
            price = float(payload["price_total"])
            price_score = max(0.0, min(1.0, 1.0 - (price / budget)))

            delivery_days = int(payload["delivery_days"])
            target = envelope.disclosure.get("desired_within_days")
            if target is None:
                delivery_score = 1.0 / (1.0 + (delivery_days / 7.0))
            elif target == 0:
                delivery_score = 1.0 if delivery_days == 0 else 0.0
            elif delivery_days <= target:
                delivery_score = 1.0
            else:
                delivery_score = max(0.0, 1.0 - ((delivery_days - target) / float(target)))

            return_score = min(float(payload["return_window_days"]) / 30.0, 1.0)
            cancellation_score = 1.0 if payload["cancellation_allowed"] else 0.0
            reversibility_score = (return_score + cancellation_score) / 2.0
            policy = envelope.ranking_policy
            score = (
                float(policy["price_weight"]) * price_score
                + float(policy["delivery_weight"]) * delivery_score
                + float(policy["reversibility_weight"]) * reversibility_score
            )
            components = {
                "price": round(price_score, 6),
                "delivery": round(delivery_score, 6),
                "reversibility": round(reversibility_score, 6),
            }
            fiduciary_score = round(score, 6)
        else:
            components = None
            fiduciary_score = None

        return {
            "offer_id": offer.offer_id,
            "responder_id": offer.responder_id,
            "responder_label": offer.responder_label,
            "identity_assurance": "key_possession_only",
            "offer_hash": offer.offer_hash,
            "eligible": eligible,
            "eligibility_reasons": offer.eligibility.get("reasons", []),
            "price_total": payload["price_total"],
            "currency": payload["currency"],
            "delivery_days": payload["delivery_days"],
            "return_window_days": payload["return_window_days"],
            "cancellation_allowed": payload["cancellation_allowed"],
            "seller_asserted_features": payload["features"],
            "commission": payload["commission"],
            "commission_excluded_from_ranking": True,
            "score_components": components,
            "fiduciary_score": fiduciary_score,
        }
