from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from ..collective_models import CollectiveIntentMembership
from ..collective_offer_models import CollectiveMarketOffer, CollectiveMarketWindow, CollectiveOfferEvaluation
from ..market_models import PrivateIntentEnvelope
from ..models import User
from ..quorum_models import CollectiveConditionalCommitment
from ..world_schemas import EventCreate
from .collective_offers import CollectiveOfferService
from .policy import sha256_dict
from .world_model import WorldModelService

PUBLIC_COMMITMENT_THRESHOLD = 10


def _safe_quorum_privacy() -> dict:
    return {
        "minimum_distinct_committed_users_for_publication": PUBLIC_COMMITMENT_THRESHOLD,
        "distinct_users_only": True,
        "user_ids_included": False,
        "membership_ids_included": False,
        "commitment_ids_included": False,
        "evaluation_ids_included": False,
        "envelope_ids_included": False,
        "individual_quantities_included": False,
        "individual_conditions_included": False,
        "formal_differential_privacy": False,
    }


class CollectiveQuorumService:
    def __init__(self, db: Session):
        self.db = db

    def commit(
        self,
        user: User,
        membership: CollectiveIntentMembership,
        offer: CollectiveMarketOffer,
        confirm: str,
    ) -> CollectiveConditionalCommitment:
        if membership.user_id != user.id or membership.status != "active":
            raise ValueError("active collective membership does not belong to user")
        required = f"CONDITIONALLY COMMIT {offer.offer_id} {offer.offer_hash[-12:]}"
        if confirm != required:
            raise ValueError(f"confirmation must equal: {required}")
        if offer.status != "group_eligible" or not offer.group_eligibility.get("eligible"):
            raise ValueError("collective offer is not group-eligible")
        if offer.valid_until <= datetime.utcnow():
            raise ValueError("collective offer is expired")

        window = self.db.query(CollectiveMarketWindow).filter(CollectiveMarketWindow.id == offer.window_id).one()
        CollectiveOfferService(self.db)._validate_current_window(window)
        if membership.cohort_id != window.cohort_id:
            raise ValueError("membership does not belong to offer cohort")

        evaluation = CollectiveOfferService(self.db).evaluate_for_user(user, membership, offer)
        if not evaluation.provisional_eligible:
            raise ValueError("private agent evaluation does not support conditional commitment")

        envelope = (
            self.db.query(PrivateIntentEnvelope)
            .filter(PrivateIntentEnvelope.id == membership.envelope_db_id)
            .one_or_none()
        )
        if not envelope:
            raise ValueError("private intent envelope no longer exists")
        quantity = int(envelope.disclosure["quantity"])
        conditions = {
            "offer_hash": offer.offer_hash,
            "source_set_hash": window.source_set_hash,
            "aggregate_hash": window.aggregate_hash,
            "envelope_hash": envelope.envelope_hash,
            "quantity": quantity,
            "unit_price": offer.payload["unit_price"],
            "currency": offer.payload["currency"],
            "minimum_collective_quantity": offer.payload["minimum_collective_quantity"],
            "maximum_collective_quantity": offer.payload["maximum_collective_quantity"],
            "offer_valid_until": offer.payload["valid_until_epoch"],
        }
        conditions_hash = sha256_dict(conditions)
        existing = (
            self.db.query(CollectiveConditionalCommitment)
            .filter(
                CollectiveConditionalCommitment.user_id == user.id,
                CollectiveConditionalCommitment.offer_db_id == offer.id,
            )
            .one_or_none()
        )
        if existing:
            commitment = existing
            commitment.membership_id = membership.id
            commitment.evaluation_id = evaluation.id
            commitment.offer_hash = offer.offer_hash
            commitment.source_set_hash = window.source_set_hash
            commitment.aggregate_hash = window.aggregate_hash
            commitment.envelope_hash = envelope.envelope_hash
            commitment.conditions_hash = conditions_hash
            commitment.quantity = quantity
            commitment.status = "active"
            commitment.created_at = datetime.utcnow()
            commitment.revoked_at = None
        else:
            commitment = CollectiveConditionalCommitment(
                user_id=user.id,
                membership_id=membership.id,
                offer_db_id=offer.id,
                evaluation_id=evaluation.id,
                commitment_id=uuid.uuid4().hex,
                offer_hash=offer.offer_hash,
                source_set_hash=window.source_set_hash,
                aggregate_hash=window.aggregate_hash,
                envelope_hash=envelope.envelope_hash,
                conditions_hash=conditions_hash,
                quantity=quantity,
                status="active",
            )
            self.db.add(commitment)
        self.db.flush()
        WorldModelService(self.db).append_event(
            user,
            EventCreate(
                event_type="collective.conditional_commitment_created",
                source="user",
                subject_type="collective_conditional_commitment",
                subject_id=commitment.commitment_id,
                payload={
                    "offer_id": offer.offer_id,
                    "conditions_hash": commitment.conditions_hash,
                    "quantity": commitment.quantity,
                    "payment_created": False,
                    "order_created": False,
                    "identity_shared_with_responder": False,
                },
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(commitment)
        return commitment

    def revoke(
        self,
        user: User,
        commitment: CollectiveConditionalCommitment,
        confirm: str,
    ) -> CollectiveConditionalCommitment:
        if commitment.user_id != user.id:
            raise ValueError("conditional commitment does not belong to user")
        required = f"REVOKE CONDITIONAL COMMITMENT {commitment.commitment_id}"
        if confirm != required:
            raise ValueError(f"confirmation must equal: {required}")
        if commitment.status == "active":
            commitment.status = "revoked"
            commitment.revoked_at = datetime.utcnow()
            WorldModelService(self.db).append_event(
                user,
                EventCreate(
                    event_type="collective.conditional_commitment_revoked",
                    source="user",
                    subject_type="collective_conditional_commitment",
                    subject_id=commitment.commitment_id,
                    payload={"identity_shared_with_responder": False},
                ),
                commit=False,
            )
            self.db.commit()
            self.db.refresh(commitment)
        return commitment

    def _current_offer_or_none(self, offer: CollectiveMarketOffer) -> CollectiveMarketWindow | None:
        if offer.status != "group_eligible" or not offer.group_eligibility.get("eligible"):
            return None
        if offer.valid_until <= datetime.utcnow():
            return None
        window = self.db.query(CollectiveMarketWindow).filter(CollectiveMarketWindow.id == offer.window_id).one_or_none()
        if not window:
            return None
        try:
            CollectiveOfferService(self.db)._validate_current_window(window)
        except ValueError:
            return None
        return window

    def quorum(self, offer: CollectiveMarketOffer) -> dict:
        privacy = _safe_quorum_privacy()
        window = self._current_offer_or_none(offer)
        if not window:
            return {
                "offer_id": offer.offer_id,
                "published": False,
                "state": "offer_or_collective_snapshot_not_current",
                "committed_user_count": None,
                "committed_quantity": None,
                "commercial_minimum_met": None,
                "quorum_publicly_confirmed": False,
                "privacy": privacy,
                "payment_created": False,
                "order_created": False,
            }

        rows = (
            self.db.query(CollectiveConditionalCommitment)
            .filter(
                CollectiveConditionalCommitment.offer_db_id == offer.id,
                CollectiveConditionalCommitment.status == "active",
            )
            .all()
        )
        valid_by_user: dict[int, CollectiveConditionalCommitment] = {}
        for commitment in rows:
            membership = (
                self.db.query(CollectiveIntentMembership)
                .filter(CollectiveIntentMembership.id == commitment.membership_id)
                .one_or_none()
            )
            evaluation = (
                self.db.query(CollectiveOfferEvaluation)
                .filter(CollectiveOfferEvaluation.id == commitment.evaluation_id)
                .one_or_none()
            )
            envelope = None
            if membership:
                envelope = (
                    self.db.query(PrivateIntentEnvelope)
                    .filter(PrivateIntentEnvelope.id == membership.envelope_db_id)
                    .one_or_none()
                )
            valid = bool(
                membership
                and membership.status == "active"
                and membership.cohort_id == window.cohort_id
                and evaluation
                and evaluation.user_id == commitment.user_id
                and evaluation.offer_db_id == offer.id
                and evaluation.provisional_eligible
                and envelope
                and commitment.offer_hash == offer.offer_hash
                and commitment.source_set_hash == window.source_set_hash
                and commitment.aggregate_hash == window.aggregate_hash
                and commitment.envelope_hash == envelope.envelope_hash
                and commitment.quantity == int(envelope.disclosure["quantity"])
            )
            if valid:
                valid_by_user[commitment.user_id] = commitment

        commitments = list(valid_by_user.values())
        committed_users = len(commitments)
        if committed_users < PUBLIC_COMMITMENT_THRESHOLD:
            return {
                "offer_id": offer.offer_id,
                "published": False,
                "state": "below_commitment_privacy_threshold",
                "committed_user_count": None,
                "committed_quantity": None,
                "commercial_minimum_met": None,
                "quorum_publicly_confirmed": False,
                "privacy": privacy,
                "payment_created": False,
                "order_created": False,
            }

        committed_quantity = sum(item.quantity for item in commitments)
        minimum_quantity = int(offer.payload["minimum_collective_quantity"])
        maximum_quantity = int(offer.payload["maximum_collective_quantity"])
        commercial_minimum_met = committed_quantity >= minimum_quantity
        capacity_exceeded = committed_quantity > maximum_quantity
        commitment_set_hash = sha256_dict(
            {"conditions": sorted(item.conditions_hash for item in commitments)}
        )
        return {
            "offer_id": offer.offer_id,
            "published": True,
            "state": "commitment_privacy_threshold_met",
            "committed_user_count": committed_users,
            "committed_quantity": committed_quantity,
            "commercial_minimum_quantity": minimum_quantity,
            "commercial_maximum_quantity": maximum_quantity,
            "commercial_minimum_met": commercial_minimum_met,
            "capacity_exceeded": capacity_exceeded,
            "allocation_required": capacity_exceeded,
            "quorum_publicly_confirmed": commercial_minimum_met,
            "commitment_set_hash": commitment_set_hash,
            "privacy": privacy,
            "payment_created": False,
            "order_created": False,
        }
