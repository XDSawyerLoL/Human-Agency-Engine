from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from ..allocation_models import CollectiveAllocationRound, CollectivePrivateAllocation
from ..collective_models import CollectiveIntentMembership
from ..collective_offer_models import CollectiveMarketOffer, CollectiveMarketWindow, CollectiveOfferEvaluation
from ..market_models import PrivateIntentEnvelope
from ..models import User
from ..quorum_models import CollectiveConditionalCommitment
from ..world_schemas import EventCreate
from .collective_offers import CollectiveOfferService
from .policy import sha256_dict
from .quorum import PUBLIC_COMMITMENT_THRESHOLD
from .world_model import WorldModelService

ALLOCATION_ALGORITHM_VERSION = "hae-fair-round-robin-v1"


class CollectiveAllocationService:
    def __init__(self, db: Session):
        self.db = db

    def _current_state(
        self,
        offer: CollectiveMarketOffer,
        *,
        lock: bool = False,
    ) -> tuple[CollectiveMarketWindow, list[CollectiveConditionalCommitment], str, int]:
        query = self.db.query(CollectiveMarketOffer).filter(CollectiveMarketOffer.id == offer.id)
        locked_offer = query.with_for_update().one() if lock else query.one()
        if locked_offer.status != "group_eligible" or not locked_offer.group_eligibility.get("eligible"):
            raise ValueError("collective offer is not group-eligible")
        if locked_offer.valid_until <= datetime.utcnow():
            raise ValueError("collective offer is expired")

        window = self.db.query(CollectiveMarketWindow).filter(CollectiveMarketWindow.id == locked_offer.window_id).one()
        CollectiveOfferService(self.db)._validate_current_window(window)

        commitments_query = self.db.query(CollectiveConditionalCommitment).filter(
            CollectiveConditionalCommitment.offer_db_id == locked_offer.id,
            CollectiveConditionalCommitment.status == "active",
        )
        commitments_rows = commitments_query.with_for_update().all() if lock else commitments_query.all()
        valid_by_user: dict[int, CollectiveConditionalCommitment] = {}
        for commitment in commitments_rows:
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
                and evaluation.offer_db_id == locked_offer.id
                and evaluation.provisional_eligible
                and envelope
                and commitment.offer_hash == locked_offer.offer_hash
                and commitment.source_set_hash == window.source_set_hash
                and commitment.aggregate_hash == window.aggregate_hash
                and commitment.envelope_hash == envelope.envelope_hash
                and commitment.quantity == int(envelope.disclosure["quantity"])
            )
            if valid:
                valid_by_user[commitment.user_id] = commitment

        commitments = list(valid_by_user.values())
        if len(commitments) < PUBLIC_COMMITMENT_THRESHOLD:
            raise ValueError("collective commitments are below privacy threshold")
        committed_quantity = sum(item.quantity for item in commitments)
        minimum_quantity = int(locked_offer.payload["minimum_collective_quantity"])
        if committed_quantity < minimum_quantity:
            raise ValueError("commercial minimum collective quantity is not met")
        commitment_set_hash = sha256_dict(
            {"conditions": sorted(item.conditions_hash for item in commitments)}
        )
        return window, commitments, commitment_set_hash, committed_quantity

    def _allocation_plan(
        self,
        offer: CollectiveMarketOffer,
        window: CollectiveMarketWindow,
        commitments: list[CollectiveConditionalCommitment],
        commitment_set_hash: str,
    ) -> tuple[str, dict[int, int], dict[int, str]]:
        seed_hash = sha256_dict(
            {
                "protocol": "hae-collective-allocation-v1",
                "algorithm": ALLOCATION_ALGORITHM_VERSION,
                "offer_hash": offer.offer_hash,
                "source_set_hash": window.source_set_hash,
                "aggregate_hash": window.aggregate_hash,
                "commitment_set_hash": commitment_set_hash,
            }
        )
        priority_hashes = {
            item.id: sha256_dict(
                {
                    "seed_hash": seed_hash,
                    "conditions_hash": item.conditions_hash,
                }
            )
            for item in commitments
        }
        ordered = sorted(commitments, key=lambda item: (priority_hashes[item.id], item.conditions_hash))
        requested = {item.id: int(item.quantity) for item in ordered}
        allocated = {item.id: 0 for item in ordered}
        capacity = min(
            int(offer.payload["maximum_collective_quantity"]),
            sum(requested.values()),
        )
        active = list(ordered)
        while capacity > 0 and active:
            remaining = {item.id: requested[item.id] - allocated[item.id] for item in active}
            minimum_remaining = min(remaining.values())
            full_rounds = min(minimum_remaining, capacity // len(active))
            if full_rounds > 0:
                for item in active:
                    allocated[item.id] += full_rounds
                capacity -= full_rounds * len(active)
                active = [item for item in active if allocated[item.id] < requested[item.id]]
                continue
            for item in active:
                if capacity <= 0:
                    break
                allocated[item.id] += 1
                capacity -= 1
            active = [item for item in active if allocated[item.id] < requested[item.id]]
        return seed_hash, allocated, priority_hashes

    def allocate(self, offer: CollectiveMarketOffer, confirm: str) -> CollectiveAllocationRound:
        window, commitments, commitment_set_hash, committed_quantity = self._current_state(offer, lock=True)
        required = f"ALLOCATE COLLECTIVE OFFER {offer.offer_id} {commitment_set_hash[-12:]}"
        if confirm != required:
            self.db.rollback()
            raise ValueError(f"confirmation must equal: {required}")

        existing = (
            self.db.query(CollectiveAllocationRound)
            .filter(
                CollectiveAllocationRound.offer_db_id == offer.id,
                CollectiveAllocationRound.commitment_set_hash == commitment_set_hash,
            )
            .one_or_none()
        )
        if existing:
            self.db.commit()
            return existing

        seed_hash, allocated, priority_hashes = self._allocation_plan(
            offer,
            window,
            commitments,
            commitment_set_hash,
        )
        capacity = int(offer.payload["maximum_collective_quantity"])
        allocated_quantity = sum(allocated.values())
        allocated_user_count = sum(1 for value in allocated.values() if value > 0)
        allocation_entry_hashes = [
            sha256_dict(
                {
                    "conditions_hash": commitment.conditions_hash,
                    "priority_hash": priority_hashes[commitment.id],
                    "requested_quantity": commitment.quantity,
                    "allocated_quantity": allocated[commitment.id],
                }
            )
            for commitment in commitments
        ]
        allocation_set_hash = sha256_dict({"entries": sorted(allocation_entry_hashes)})
        round_row = CollectiveAllocationRound(
            offer_db_id=offer.id,
            allocation_id=uuid.uuid4().hex,
            commitment_set_hash=commitment_set_hash,
            seed_hash=seed_hash,
            algorithm_version=ALLOCATION_ALGORITHM_VERSION,
            committed_user_count=len(commitments),
            committed_quantity=committed_quantity,
            capacity_quantity=capacity,
            allocated_user_count=allocated_user_count,
            allocated_quantity=allocated_quantity,
            oversubscribed=committed_quantity > capacity,
            allocation_set_hash=allocation_set_hash,
            status="allocated",
        )
        self.db.add(round_row)
        self.db.flush()

        for commitment in commitments:
            allocated_quantity_for_user = allocated[commitment.id]
            private = CollectivePrivateAllocation(
                user_id=commitment.user_id,
                allocation_round_id=round_row.id,
                commitment_id=commitment.id,
                allocation_entry_id=uuid.uuid4().hex,
                priority_hash=priority_hashes[commitment.id],
                requested_quantity=commitment.quantity,
                allocated_quantity=allocated_quantity_for_user,
                status="allocated" if allocated_quantity_for_user > 0 else "waitlisted",
            )
            self.db.add(private)
            user = self.db.query(User).filter(User.id == commitment.user_id).one()
            WorldModelService(self.db).append_event(
                user,
                EventCreate(
                    event_type="collective.private_allocation_created",
                    source="collective_allocator",
                    subject_type="collective_private_allocation",
                    subject_id=private.allocation_entry_id,
                    payload={
                        "offer_id": offer.offer_id,
                        "requested_quantity": commitment.quantity,
                        "allocated_quantity": allocated_quantity_for_user,
                        "priority_hash": private.priority_hash,
                        "identity_shared_with_responder": False,
                        "payment_created": False,
                        "order_created": False,
                    },
                ),
                commit=False,
            )
        self.db.commit()
        self.db.refresh(round_row)
        return round_row

    def effective_public_allocation(self, offer: CollectiveMarketOffer) -> dict:
        try:
            _window, commitments, commitment_set_hash, _committed_quantity = self._current_state(offer)
        except ValueError:
            return {
                "offer_id": offer.offer_id,
                "allocation_current": False,
                "state": "allocation_not_current_or_quorum_unavailable",
                "allocation": None,
                "member_identities_included": False,
                "private_allocations_included": False,
                "payment_created": False,
                "order_created": False,
            }
        round_row = (
            self.db.query(CollectiveAllocationRound)
            .filter(
                CollectiveAllocationRound.offer_db_id == offer.id,
                CollectiveAllocationRound.commitment_set_hash == commitment_set_hash,
                CollectiveAllocationRound.status == "allocated",
            )
            .one_or_none()
        )
        if not round_row:
            return {
                "offer_id": offer.offer_id,
                "allocation_current": False,
                "state": "allocation_not_created_for_current_commitment_set",
                "allocation": None,
                "member_identities_included": False,
                "private_allocations_included": False,
                "payment_created": False,
                "order_created": False,
            }
        return {
            "offer_id": offer.offer_id,
            "allocation_current": True,
            "state": "allocation_available",
            "allocation": {
                "allocation_id": round_row.allocation_id,
                "algorithm_version": round_row.algorithm_version,
                "seed_hash": round_row.seed_hash,
                "commitment_set_hash": round_row.commitment_set_hash,
                "committed_user_count": round_row.committed_user_count,
                "committed_quantity": round_row.committed_quantity,
                "capacity_quantity": round_row.capacity_quantity,
                "allocated_user_count": round_row.allocated_user_count,
                "allocated_quantity": round_row.allocated_quantity,
                "oversubscribed": round_row.oversubscribed,
                "allocation_set_hash": round_row.allocation_set_hash,
            },
            "member_identities_included": False,
            "private_allocations_included": False,
            "payment_created": False,
            "order_created": False,
        }
