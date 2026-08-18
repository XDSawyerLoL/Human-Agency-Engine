from __future__ import annotations

import math
import statistics
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from ..collective_models import CollectiveIntentCohort, CollectiveIntentMembership
from ..market_models import PrivateIntentEnvelope
from ..models import PersonalMandate, User
from ..synthesis_models import CandidateIntervention
from ..world_schemas import EventCreate
from .policy import action_fingerprint, sha256_dict
from .world_model import WorldModelService

MINIMUM_COHORT_SIZE = 10
MINIMUM_PUBLISHED_CELL_SIZE = 3
BUDGET_BUCKET_SIZE = 25.0


def _cohort_descriptor(envelope: PrivateIntentEnvelope) -> dict:
    return {
        "protocol": "hae-collective-intent-v1",
        "request_type": envelope.request_type,
        "category": envelope.category,
        "currency": envelope.disclosure["currency"],
        "country": envelope.disclosure["country"],
    }


def _contribution_payload(envelope: PrivateIntentEnvelope) -> dict:
    return {
        "envelope_hash": envelope.envelope_hash,
        "budget_max": envelope.disclosure["budget_max"],
        "quantity": envelope.disclosure["quantity"],
        "desired_within_days": envelope.disclosure.get("desired_within_days"),
    }


def _delivery_bucket(days: int | None) -> str:
    if days is None:
        return "unspecified"
    if days == 0:
        return "same_day"
    if days <= 3:
        return "1_3_days"
    if days <= 7:
        return "4_7_days"
    if days <= 14:
        return "8_14_days"
    if days <= 30:
        return "15_30_days"
    return "31_plus_days"


class CollectiveIntentService:
    def __init__(self, db: Session):
        self.db = db

    def _live_envelope(self, envelope: PrivateIntentEnvelope) -> bool:
        if envelope.status != "open" or envelope.expires_at <= datetime.utcnow():
            return False
        mandate = (
            self.db.query(PersonalMandate)
            .filter(PersonalMandate.user_id == envelope.user_id)
            .one_or_none()
        )
        if not mandate or mandate.version != envelope.mandate_version:
            return False
        candidate = (
            self.db.query(CandidateIntervention)
            .filter(CandidateIntervention.id == envelope.candidate_id)
            .one_or_none()
        )
        return bool(candidate and action_fingerprint(candidate) == envelope.candidate_fingerprint)

    def join(self, user: User, envelope: PrivateIntentEnvelope, confirm: str) -> CollectiveIntentMembership:
        if envelope.user_id != user.id:
            raise ValueError("private intent envelope does not belong to user")
        required = f"JOIN COLLECTIVE INTENT {envelope.envelope_id}"
        if confirm != required:
            raise ValueError(f"confirmation must equal: {required}")
        if not self._live_envelope(envelope):
            raise ValueError("only a live private intent can join a collective cohort")

        descriptor = _cohort_descriptor(envelope)
        cohort_key = sha256_dict(descriptor)
        cohort = (
            self.db.query(CollectiveIntentCohort)
            .filter(CollectiveIntentCohort.cohort_key == cohort_key)
            .one_or_none()
        )
        if not cohort:
            cohort = CollectiveIntentCohort(
                cohort_key=cohort_key,
                request_type=descriptor["request_type"],
                category=descriptor["category"],
                currency=descriptor["currency"],
                country=descriptor["country"],
                minimum_cohort_size=MINIMUM_COHORT_SIZE,
                status="active",
            )
            self.db.add(cohort)
            self.db.flush()

        contribution_fingerprint = sha256_dict(_contribution_payload(envelope))
        membership = (
            self.db.query(CollectiveIntentMembership)
            .filter(
                CollectiveIntentMembership.user_id == user.id,
                CollectiveIntentMembership.cohort_id == cohort.id,
            )
            .one_or_none()
        )
        if membership:
            membership.envelope_db_id = envelope.id
            membership.contribution_fingerprint = contribution_fingerprint
            membership.status = "active"
            membership.joined_at = datetime.utcnow()
            membership.left_at = None
        else:
            membership = CollectiveIntentMembership(
                user_id=user.id,
                envelope_db_id=envelope.id,
                cohort_id=cohort.id,
                membership_id=uuid.uuid4().hex,
                contribution_fingerprint=contribution_fingerprint,
                status="active",
            )
            self.db.add(membership)
        self.db.flush()
        WorldModelService(self.db).append_event(
            user,
            EventCreate(
                event_type="collective.intent_joined",
                source="user",
                subject_type="collective_membership",
                subject_id=membership.membership_id,
                payload={
                    "cohort_key": cohort.cohort_key,
                    "minimum_cohort_size": cohort.minimum_cohort_size,
                    "individual_identity_published": False,
                },
                correlation_id=f"candidate:{envelope.candidate_id}",
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(membership)
        return membership

    def leave(self, user: User, membership: CollectiveIntentMembership, confirm: str) -> CollectiveIntentMembership:
        if membership.user_id != user.id:
            raise ValueError("collective membership does not belong to user")
        required = f"LEAVE COLLECTIVE INTENT {membership.membership_id}"
        if confirm != required:
            raise ValueError(f"confirmation must equal: {required}")
        if membership.status == "active":
            membership.status = "left"
            membership.left_at = datetime.utcnow()
            WorldModelService(self.db).append_event(
                user,
                EventCreate(
                    event_type="collective.intent_left",
                    source="user",
                    subject_type="collective_membership",
                    subject_id=membership.membership_id,
                    payload={"individual_identity_published": False},
                ),
                commit=False,
            )
            self.db.commit()
            self.db.refresh(membership)
        return membership

    def aggregate(self, cohort: CollectiveIntentCohort) -> dict:
        memberships = (
            self.db.query(CollectiveIntentMembership)
            .filter(
                CollectiveIntentMembership.cohort_id == cohort.id,
                CollectiveIntentMembership.status == "active",
            )
            .order_by(CollectiveIntentMembership.joined_at.asc())
            .all()
        )
        contributions: list[tuple[CollectiveIntentMembership, PrivateIntentEnvelope]] = []
        for membership in memberships:
            envelope = (
                self.db.query(PrivateIntentEnvelope)
                .filter(PrivateIntentEnvelope.id == membership.envelope_db_id)
                .one_or_none()
            )
            if envelope and self._live_envelope(envelope):
                contributions.append((membership, envelope))

        # Database uniqueness ensures one membership per user and cohort, but keep
        # the distinct-user invariant explicit in case the storage model changes.
        by_user: dict[int, tuple[CollectiveIntentMembership, PrivateIntentEnvelope]] = {}
        for membership, envelope in contributions:
            by_user[membership.user_id] = (membership, envelope)
        contributions = list(by_user.values())
        cohort_size = len(contributions)

        privacy = {
            "minimum_cohort_size": cohort.minimum_cohort_size,
            "minimum_published_cell_size": MINIMUM_PUBLISHED_CELL_SIZE,
            "distinct_users_only": True,
            "user_ids_included": False,
            "envelope_ids_included": False,
            "subject_refs_included": False,
            "individual_contributions_included": False,
            "formal_differential_privacy": False,
        }
        if cohort_size < cohort.minimum_cohort_size:
            return {
                "cohort_key": cohort.cohort_key,
                "published": False,
                "state": "below_privacy_threshold",
                "cohort_size": None,
                "descriptor": None,
                "aggregate": None,
                "privacy": privacy,
            }

        budgets = [float(envelope.disclosure["budget_max"]) for _, envelope in contributions]
        quantities = [int(envelope.disclosure["quantity"]) for _, envelope in contributions]
        median_budget = float(statistics.median(budgets))
        budget_bucket_min = math.floor(median_budget / BUDGET_BUCKET_SIZE) * BUDGET_BUCKET_SIZE
        budget_bucket = {
            "min": budget_bucket_min,
            "max_exclusive": budget_bucket_min + BUDGET_BUCKET_SIZE,
            "currency": cohort.currency,
        }

        delivery_counts: dict[str, int] = {}
        for _, envelope in contributions:
            bucket = _delivery_bucket(envelope.disclosure.get("desired_within_days"))
            delivery_counts[bucket] = delivery_counts.get(bucket, 0) + 1
        published_delivery: dict[str, int] = {}
        suppressed = 0
        for bucket, count in sorted(delivery_counts.items()):
            if count >= MINIMUM_PUBLISHED_CELL_SIZE:
                published_delivery[bucket] = count
            else:
                suppressed += count
        if suppressed:
            published_delivery["suppressed"] = suppressed

        source_set_hash = sha256_dict(
            {"contributions": sorted(membership.contribution_fingerprint for membership, _ in contributions)}
        )
        return {
            "cohort_key": cohort.cohort_key,
            "published": True,
            "state": "privacy_threshold_met",
            "cohort_size": cohort_size,
            "descriptor": {
                "request_type": cohort.request_type,
                "category": cohort.category,
                "currency": cohort.currency,
                "country": cohort.country,
            },
            "aggregate": {
                "total_quantity": sum(quantities),
                "median_budget_bucket": budget_bucket,
                "delivery_preference_buckets": published_delivery,
                "source_set_hash": source_set_hash,
            },
            "privacy": privacy,
        }
