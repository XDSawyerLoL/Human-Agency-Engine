from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy.orm import Session

from ..collective_models import CollectiveIntentCohort, CollectiveIntentMembership
from ..collective_offer_models import (
    CollectiveMarketOffer,
    CollectiveMarketWindow,
    CollectiveOfferEvaluation,
)
from ..collective_offer_schemas import CollectiveMarketOpen, CollectiveOfferSubmit
from ..market_models import PrivateIntentEnvelope
from ..models import User
from ..world_schemas import EventCreate
from .collective import CollectiveIntentService
from .policy import canonical_json, sha256_dict
from .world_model import WorldModelService

COLLECTIVE_OFFER_PROTOCOL = "hae-collective-offer-v1"
MAX_FEATURE_LENGTH = 80
MAX_FUTURE_OFFER_SECONDS = 7 * 24 * 60 * 60


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


def public_collective_window(window: CollectiveMarketWindow) -> dict:
    return {
        "protocol": COLLECTIVE_OFFER_PROTOCOL,
        "window_id": window.window_id,
        "source_set_hash": window.source_set_hash,
        "aggregate_hash": window.aggregate_hash,
        "challenge_nonce": window.challenge_nonce,
        "snapshot": window.public_snapshot,
        "status": window.status,
        "expires_at": _epoch(window.expires_at),
        "privacy": {
            "member_identities_included": False,
            "membership_ids_included": False,
            "envelope_ids_included": False,
            "subject_refs_included": False,
            "individual_budgets_included": False,
            "individual_evaluations_included": False,
        },
    }


def _normalized_offer(request: CollectiveOfferSubmit) -> tuple[dict, bytes, str]:
    try:
        public_raw = _b64u_decode(request.public_key_b64)
        if len(public_raw) != 32:
            raise ValueError("responder Ed25519 public key must be 32 bytes")
        Ed25519PublicKey.from_public_bytes(public_raw)
    except Exception as exc:
        if isinstance(exc, ValueError) and "32 bytes" in str(exc):
            raise
        raise ValueError("invalid responder Ed25519 public key") from exc

    currency = request.currency.upper()
    if not currency.isalpha():
        raise ValueError("offer currency must be alphabetic")
    commission_currency = request.commission_currency.upper() if request.commission_currency else currency
    if request.commission_per_unit > 0 and commission_currency != currency:
        raise ValueError("V1 commission currency must match offer currency")
    if request.minimum_collective_quantity > request.maximum_collective_quantity:
        raise ValueError("minimum collective quantity cannot exceed maximum collective quantity")
    features = sorted({_clean_feature(item) for item in request.features})
    responder_id = _key_fingerprint(public_raw)
    data = {
        "offer_id": request.offer_id,
        "responder_label": " ".join(request.responder_label.strip().split())[:255],
        "unit_price": round(float(request.unit_price), 6),
        "currency": currency,
        "minimum_collective_quantity": request.minimum_collective_quantity,
        "maximum_collective_quantity": request.maximum_collective_quantity,
        "delivery_days": request.delivery_days,
        "return_window_days": request.return_window_days,
        "cancellation_allowed": request.cancellation_allowed,
        "available": request.available,
        "features": features,
        "condition": request.condition,
        "commission": {
            "per_unit": round(float(request.commission_per_unit), 6),
            "currency": commission_currency,
        },
        "valid_until_epoch": request.valid_until_epoch,
    }
    return data, public_raw, responder_id


def collective_offer_signed_payload(
    window: CollectiveMarketWindow,
    request: CollectiveOfferSubmit,
) -> dict:
    offer, _public_raw, responder_id = _normalized_offer(request)
    return {
        "protocol": COLLECTIVE_OFFER_PROTOCOL,
        "window": {
            "window_id": window.window_id,
            "source_set_hash": window.source_set_hash,
            "aggregate_hash": window.aggregate_hash,
            "challenge_nonce": window.challenge_nonce,
        },
        "responder": {
            "responder_id": responder_id,
            "public_key_b64": request.public_key_b64,
        },
        "offer": offer,
    }


class CollectiveOfferService:
    def __init__(self, db: Session):
        self.db = db

    def open_window(self, request: CollectiveMarketOpen) -> CollectiveMarketWindow:
        cohort = (
            self.db.query(CollectiveIntentCohort)
            .filter(CollectiveIntentCohort.cohort_key == request.cohort_key)
            .one_or_none()
        )
        if not cohort:
            raise ValueError("collective cohort not found")
        required = f"OPEN COLLECTIVE MARKET {cohort.cohort_key}"
        if request.confirm != required:
            raise ValueError(f"confirmation must equal: {required}")

        aggregate = CollectiveIntentService(self.db).aggregate(cohort)
        if not aggregate["published"]:
            raise ValueError("collective cohort is below privacy threshold")
        snapshot = {
            "cohort_key": aggregate["cohort_key"],
            "cohort_size": aggregate["cohort_size"],
            "descriptor": aggregate["descriptor"],
            "aggregate": aggregate["aggregate"],
            "privacy": aggregate["privacy"],
        }
        source_set_hash = aggregate["aggregate"]["source_set_hash"]
        window = CollectiveMarketWindow(
            cohort_id=cohort.id,
            window_id=uuid.uuid4().hex,
            source_set_hash=source_set_hash,
            aggregate_hash=sha256_dict(snapshot),
            challenge_nonce=secrets.token_urlsafe(24),
            public_snapshot=snapshot,
            status="open",
            expires_at=datetime.utcnow() + timedelta(seconds=request.expires_in_seconds),
        )
        self.db.add(window)
        self.db.commit()
        self.db.refresh(window)
        return window

    def _validate_current_window(self, window: CollectiveMarketWindow) -> dict:
        if window.status != "open":
            raise ValueError("collective market window is not open")
        if window.expires_at <= datetime.utcnow():
            window.status = "expired"
            self.db.commit()
            raise ValueError("collective market window is expired")
        cohort = self.db.query(CollectiveIntentCohort).filter(CollectiveIntentCohort.id == window.cohort_id).one()
        aggregate = CollectiveIntentService(self.db).aggregate(cohort)
        if not aggregate["published"]:
            window.status = "stale"
            self.db.commit()
            raise ValueError("collective market window is stale because privacy threshold is no longer met")
        if aggregate["aggregate"]["source_set_hash"] != window.source_set_hash:
            window.status = "stale"
            self.db.commit()
            raise ValueError("collective market window is stale because cohort composition changed")
        snapshot = {
            "cohort_key": aggregate["cohort_key"],
            "cohort_size": aggregate["cohort_size"],
            "descriptor": aggregate["descriptor"],
            "aggregate": aggregate["aggregate"],
            "privacy": aggregate["privacy"],
        }
        if sha256_dict(snapshot) != window.aggregate_hash:
            window.status = "stale"
            self.db.commit()
            raise ValueError("collective market window is stale because aggregate snapshot changed")
        return aggregate

    def submit_offer(self, window: CollectiveMarketWindow, request: CollectiveOfferSubmit) -> CollectiveMarketOffer:
        aggregate = self._validate_current_window(window)
        offer_data, public_raw, responder_id = _normalized_offer(request)
        now_epoch = int(datetime.now(timezone.utc).timestamp())
        if request.valid_until_epoch <= now_epoch:
            raise ValueError("collective offer is already expired")
        if request.valid_until_epoch > now_epoch + MAX_FUTURE_OFFER_SECONDS:
            raise ValueError("collective offer validity exceeds V1 maximum")
        if request.valid_until_epoch > _epoch(window.expires_at):
            raise ValueError("collective offer cannot outlive its market window")

        signed_payload = collective_offer_signed_payload(window, request)
        try:
            signature = _b64u_decode(request.signature_b64)
            Ed25519PublicKey.from_public_bytes(public_raw).verify(signature, canonical_json(signed_payload))
        except (InvalidSignature, ValueError, TypeError) as exc:
            raise ValueError("invalid signed collective market offer") from exc

        offer_hash = sha256_dict(signed_payload)
        existing = (
            self.db.query(CollectiveMarketOffer)
            .filter(CollectiveMarketOffer.offer_id == request.offer_id)
            .one_or_none()
        )
        if existing:
            if existing.offer_hash != offer_hash:
                raise ValueError("collective offer_id replayed with different signed payload")
            return existing

        reasons: list[str] = []
        descriptor = aggregate["descriptor"]
        total_demand_quantity = int(aggregate["aggregate"]["total_quantity"])
        if not offer_data["available"]:
            reasons.append("offer not available")
        if offer_data["currency"] != descriptor["currency"]:
            reasons.append("currency mismatch")
        if offer_data["minimum_collective_quantity"] > total_demand_quantity:
            reasons.append("minimum collective quantity exceeds current demand-pool quantity")
        if offer_data["maximum_collective_quantity"] < 1:
            reasons.append("maximum collective quantity is invalid")
        group_eligibility = {
            "eligible": not reasons,
            "reasons": reasons,
            "demand_pool_quantity": total_demand_quantity,
            "demand_is_not_commitment": True,
            "commission_considered": False,
        }
        offer = CollectiveMarketOffer(
            window_id=window.id,
            offer_id=request.offer_id,
            responder_id=responder_id,
            responder_label=offer_data["responder_label"],
            public_key_b64=request.public_key_b64,
            signature_b64=request.signature_b64,
            offer_hash=offer_hash,
            payload=offer_data,
            group_eligibility=group_eligibility,
            status="group_eligible" if group_eligibility["eligible"] else "group_ineligible",
            valid_until=datetime.utcfromtimestamp(request.valid_until_epoch),
        )
        self.db.add(offer)
        self.db.commit()
        self.db.refresh(offer)
        return offer

    def evaluate_for_user(
        self,
        user: User,
        membership: CollectiveIntentMembership,
        offer: CollectiveMarketOffer,
    ) -> CollectiveOfferEvaluation:
        if membership.user_id != user.id or membership.status != "active":
            raise ValueError("active collective membership does not belong to user")
        window = self.db.query(CollectiveMarketWindow).filter(CollectiveMarketWindow.id == offer.window_id).one()
        self._validate_current_window(window)
        if membership.cohort_id != window.cohort_id:
            raise ValueError("membership does not belong to offer cohort")
        if offer.valid_until <= datetime.utcnow():
            offer.status = "expired"
            self.db.commit()
            raise ValueError("collective offer is expired")

        envelope = (
            self.db.query(PrivateIntentEnvelope)
            .filter(PrivateIntentEnvelope.id == membership.envelope_db_id)
            .one_or_none()
        )
        if not envelope or not CollectiveIntentService(self.db)._live_envelope(envelope):
            raise ValueError("membership private intent is no longer live")

        payload = offer.payload
        disclosure = envelope.disclosure
        reasons = list(offer.group_eligibility.get("reasons", []))
        quantity = int(disclosure["quantity"])
        total_price = float(payload["unit_price"]) * quantity
        if payload["currency"] != disclosure["currency"]:
            reasons.append("private currency mismatch")
        if total_price > float(disclosure["budget_max"]):
            reasons.append("private budget ceiling exceeded")
        if quantity > int(payload["maximum_collective_quantity"]):
            reasons.append("individual quantity exceeds offer maximum")
        condition = disclosure.get("condition", "any")
        if condition != "any" and payload["condition"] not in {condition, "not_applicable"}:
            reasons.append("private condition mismatch")
        requested_features = set(disclosure.get("required_features") or [])
        offered_features = set(payload.get("features") or [])
        missing = sorted(requested_features - offered_features)
        if missing:
            reasons.append("missing seller-asserted features: " + ", ".join(missing))

        provisional_eligible = not reasons
        if provisional_eligible:
            budget = float(disclosure["budget_max"])
            price_score = max(0.0, min(1.0, 1.0 - (total_price / budget)))
            target = disclosure.get("desired_within_days")
            delivery_days = int(payload["delivery_days"])
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
            components = {}
            fiduciary_score = None

        existing = (
            self.db.query(CollectiveOfferEvaluation)
            .filter(
                CollectiveOfferEvaluation.membership_id == membership.id,
                CollectiveOfferEvaluation.offer_db_id == offer.id,
            )
            .one_or_none()
        )
        if existing:
            evaluation = existing
            evaluation.envelope_hash = envelope.envelope_hash
            evaluation.provisional_eligible = provisional_eligible
            evaluation.reasons = reasons
            evaluation.score_components = components
            evaluation.fiduciary_score = fiduciary_score
            evaluation.commission_excluded = True
            evaluation.created_at = datetime.utcnow()
        else:
            evaluation = CollectiveOfferEvaluation(
                user_id=user.id,
                membership_id=membership.id,
                offer_db_id=offer.id,
                evaluation_id=uuid.uuid4().hex,
                envelope_hash=envelope.envelope_hash,
                provisional_eligible=provisional_eligible,
                reasons=reasons,
                score_components=components,
                fiduciary_score=fiduciary_score,
                commission_excluded=True,
            )
            self.db.add(evaluation)
        self.db.flush()
        WorldModelService(self.db).append_event(
            user,
            EventCreate(
                event_type="collective.offer_evaluated_privately",
                source="personal_agent",
                subject_type="collective_offer_evaluation",
                subject_id=evaluation.evaluation_id,
                payload={
                    "offer_id": offer.offer_id,
                    "provisional_eligible": provisional_eligible,
                    "commission_excluded": True,
                    "evaluation_shared_with_responder": False,
                },
                correlation_id=f"candidate:{envelope.candidate_id}",
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(evaluation)
        return evaluation
