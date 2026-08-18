from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..acceptance_models import CollectiveAllocationDecision
from ..allocation_models import CollectiveAllocationRound, CollectivePrivateAllocation
from ..collective_offer_models import CollectiveMarketOffer
from ..quorum_models import CollectiveConditionalCommitment
from ..settlement_models import CollectiveSettlementReadinessReceipt
from .allocation import CollectiveAllocationService
from .policy import sha256_dict

MINIMUM_SETTLEMENT_ANONYMITY_SET = 10


@dataclass
class SettlementSnapshot:
    round_row: CollectiveAllocationRound
    accepted_set_hash: str
    accepted_user_count: int
    accepted_quantity: int
    allocated_user_count: int
    allocated_quantity: int
    unit_price: float
    currency: str
    exact_total_amount: float
    all_allocated_users_accepted: bool
    commercial_minimum_met: bool
    capacity_ok: bool
    settlement_ready: bool
    reasons: list[str]


class CollectiveSettlementService:
    def __init__(self, db: Session):
        self.db = db

    def _snapshot(self, offer: CollectiveMarketOffer) -> SettlementSnapshot:
        _window, _commitments, commitment_set_hash, _ = CollectiveAllocationService(
            self.db
        )._current_state(offer)
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
            raise ValueError("current collective commitment set has not been allocated")

        private_allocations = (
            self.db.query(CollectivePrivateAllocation)
            .filter(
                CollectivePrivateAllocation.allocation_round_id == round_row.id,
                CollectivePrivateAllocation.allocated_quantity > 0,
                CollectivePrivateAllocation.status == "allocated",
            )
            .all()
        )
        if len(private_allocations) != round_row.allocated_user_count:
            raise ValueError("private allocation count does not match public allocation round")
        if sum(item.allocated_quantity for item in private_allocations) != round_row.allocated_quantity:
            raise ValueError("private allocated quantity does not match public allocation round")

        accepted = []
        for private in private_allocations:
            decision = (
                self.db.query(CollectiveAllocationDecision)
                .filter(
                    CollectiveAllocationDecision.private_allocation_id == private.id,
                    CollectiveAllocationDecision.decision == "accepted",
                    CollectiveAllocationDecision.revoked_at.is_(None),
                )
                .one_or_none()
            )
            if not decision:
                continue
            commitment = (
                self.db.query(CollectiveConditionalCommitment)
                .filter(CollectiveConditionalCommitment.id == private.commitment_id)
                .one()
            )
            valid = bool(
                commitment.status == "active"
                and decision.user_id == private.user_id
                and decision.commitment_id == commitment.id
                and decision.allocation_set_hash == round_row.allocation_set_hash
                and decision.offer_hash == offer.offer_hash
                and decision.conditions_hash == commitment.conditions_hash
                and decision.allocated_quantity == private.allocated_quantity
                and decision.currency == offer.payload["currency"]
            )
            if valid:
                accepted.append((private, decision))

        accepted_by_user = {private.user_id: (private, decision) for private, decision in accepted}
        accepted = list(accepted_by_user.values())
        accepted_user_count = len(accepted)
        accepted_quantity = sum(private.allocated_quantity for private, _ in accepted)
        allocated_user_count = len(private_allocations)
        allocated_quantity = sum(item.allocated_quantity for item in private_allocations)
        accepted_set_hash = sha256_dict(
            {"decisions": sorted(decision.decision_hash for _, decision in accepted)}
        )

        minimum_quantity = int(offer.payload["minimum_collective_quantity"])
        maximum_quantity = int(offer.payload["maximum_collective_quantity"])
        all_allocated_users_accepted = (
            accepted_user_count == allocated_user_count
            and accepted_quantity == allocated_quantity
        )
        commercial_minimum_met = accepted_quantity >= minimum_quantity
        capacity_ok = accepted_quantity <= maximum_quantity
        reasons: list[str] = []
        if accepted_user_count < MINIMUM_SETTLEMENT_ANONYMITY_SET:
            reasons.append("accepted anonymity set is below default settlement threshold")
        if not all_allocated_users_accepted:
            reasons.append("not every positive allocation has an effective acceptance")
        if not commercial_minimum_met:
            reasons.append("accepted quantity is below merchant collective minimum")
        if not capacity_ok:
            reasons.append("accepted quantity exceeds merchant collective capacity")

        settlement_ready = not reasons
        unit_price = round(float(offer.payload["unit_price"]), 6)
        exact_total_amount = round(unit_price * accepted_quantity, 6)
        return SettlementSnapshot(
            round_row=round_row,
            accepted_set_hash=accepted_set_hash,
            accepted_user_count=accepted_user_count,
            accepted_quantity=accepted_quantity,
            allocated_user_count=allocated_user_count,
            allocated_quantity=allocated_quantity,
            unit_price=unit_price,
            currency=offer.payload["currency"],
            exact_total_amount=exact_total_amount,
            all_allocated_users_accepted=all_allocated_users_accepted,
            commercial_minimum_met=commercial_minimum_met,
            capacity_ok=capacity_ok,
            settlement_ready=settlement_ready,
            reasons=reasons,
        )

    def assess(self, offer: CollectiveMarketOffer) -> CollectiveSettlementReadinessReceipt:
        snapshot = self._snapshot(offer)
        existing = (
            self.db.query(CollectiveSettlementReadinessReceipt)
            .filter(
                CollectiveSettlementReadinessReceipt.allocation_round_id == snapshot.round_row.id,
                CollectiveSettlementReadinessReceipt.accepted_set_hash == snapshot.accepted_set_hash,
            )
            .one_or_none()
        )
        if existing:
            return existing

        receipt = CollectiveSettlementReadinessReceipt(
            offer_db_id=offer.id,
            allocation_round_id=snapshot.round_row.id,
            receipt_id=uuid.uuid4().hex,
            allocation_set_hash=snapshot.round_row.allocation_set_hash,
            commitment_set_hash=snapshot.round_row.commitment_set_hash,
            accepted_set_hash=snapshot.accepted_set_hash,
            accepted_user_count=snapshot.accepted_user_count,
            accepted_quantity=snapshot.accepted_quantity,
            allocated_user_count=snapshot.allocated_user_count,
            allocated_quantity=snapshot.allocated_quantity,
            unit_price=snapshot.unit_price,
            currency=snapshot.currency,
            exact_total_amount=snapshot.exact_total_amount,
            minimum_anonymity_set=MINIMUM_SETTLEMENT_ANONYMITY_SET,
            all_allocated_users_accepted=snapshot.all_allocated_users_accepted,
            commercial_minimum_met=snapshot.commercial_minimum_met,
            capacity_ok=snapshot.capacity_ok,
            settlement_ready=snapshot.settlement_ready,
            reasons=snapshot.reasons,
            external_dispatch_enabled=False,
            payment_created=False,
            order_created=False,
        )
        self.db.add(receipt)
        self.db.commit()
        self.db.refresh(receipt)
        return receipt

    def effective_receipt(self, offer: CollectiveMarketOffer) -> CollectiveSettlementReadinessReceipt | None:
        try:
            snapshot = self._snapshot(offer)
        except ValueError:
            return None
        return (
            self.db.query(CollectiveSettlementReadinessReceipt)
            .filter(
                CollectiveSettlementReadinessReceipt.allocation_round_id == snapshot.round_row.id,
                CollectiveSettlementReadinessReceipt.accepted_set_hash == snapshot.accepted_set_hash,
            )
            .one_or_none()
        )

    @staticmethod
    def public_view(
        offer: CollectiveMarketOffer,
        receipt: CollectiveSettlementReadinessReceipt | None,
    ) -> dict:
        privacy = {
            "minimum_anonymity_set": MINIMUM_SETTLEMENT_ANONYMITY_SET,
            "distinct_users_only": True,
            "user_ids_included": False,
            "allocation_entry_ids_included": False,
            "decision_ids_included": False,
            "decision_hashes_included": False,
            "private_conditions_included": False,
            "lower_anonymity_override_supported": False,
            "formal_differential_privacy": False,
        }
        if receipt is None:
            return {
                "offer_id": offer.offer_id,
                "published": False,
                "state": "no_current_assessed_settlement_readiness",
                "settlement_ready": False,
                "accepted_user_count": None,
                "accepted_quantity": None,
                "privacy": privacy,
                "external_dispatch_enabled": False,
                "payment_created": False,
                "order_created": False,
            }
        if receipt.accepted_user_count < MINIMUM_SETTLEMENT_ANONYMITY_SET:
            return {
                "offer_id": offer.offer_id,
                "receipt_id": receipt.receipt_id,
                "published": False,
                "state": "below_settlement_privacy_threshold",
                "settlement_ready": False,
                "accepted_user_count": None,
                "accepted_quantity": None,
                "allocated_user_count": None,
                "allocated_quantity": None,
                "commercial_minimum_met": None,
                "all_allocated_users_accepted": None,
                "privacy": privacy,
                "external_dispatch_enabled": False,
                "payment_created": False,
                "order_created": False,
            }

        state = (
            "ready_for_settlement_preparation"
            if receipt.settlement_ready
            else "acceptance_threshold_met_but_not_ready"
        )
        return {
            "offer_id": offer.offer_id,
            "receipt_id": receipt.receipt_id,
            "published": True,
            "state": state,
            "settlement_ready": receipt.settlement_ready,
            "accepted_user_count": receipt.accepted_user_count,
            "accepted_quantity": receipt.accepted_quantity,
            "allocated_user_count": receipt.allocated_user_count,
            "allocated_quantity": receipt.allocated_quantity,
            "unit_price": receipt.unit_price,
            "currency": receipt.currency,
            "exact_total_amount": receipt.exact_total_amount,
            "commercial_minimum_met": receipt.commercial_minimum_met,
            "capacity_ok": receipt.capacity_ok,
            "all_allocated_users_accepted": receipt.all_allocated_users_accepted,
            "allocation_set_hash": receipt.allocation_set_hash,
            "commitment_set_hash": receipt.commitment_set_hash,
            "accepted_set_hash": receipt.accepted_set_hash,
            "privacy": privacy,
            "external_dispatch_enabled": False,
            "payment_created": False,
            "order_created": False,
        }
