from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from ..acceptance_models import CollectiveAllocationDecision
from ..allocation_models import CollectiveAllocationRound, CollectivePrivateAllocation
from ..collective_models import CollectiveIntentMembership
from ..collective_offer_models import CollectiveMarketOffer
from ..market_models import PrivateIntentEnvelope
from ..models import User
from ..quorum_models import CollectiveConditionalCommitment
from ..world_schemas import EventCreate
from .allocation import CollectiveAllocationService
from .collective import CollectiveIntentService
from .collective_offers import CollectiveOfferService
from .policy import sha256_dict
from .world_model import WorldModelService


class AllocationAcceptanceService:
    def __init__(self, db: Session):
        self.db = db

    def _context(self, user: User, allocation_entry_id: str):
        private = self.db.query(CollectivePrivateAllocation).filter(CollectivePrivateAllocation.allocation_entry_id == allocation_entry_id).one_or_none()
        if not private or private.user_id != user.id:
            raise ValueError("private allocation not found for user")
        round_row = self.db.query(CollectiveAllocationRound).filter(CollectiveAllocationRound.id == private.allocation_round_id).one()
        offer = self.db.query(CollectiveMarketOffer).filter(CollectiveMarketOffer.id == round_row.offer_db_id).one()
        commitment = self.db.query(CollectiveConditionalCommitment).filter(CollectiveConditionalCommitment.id == private.commitment_id).one()
        membership = self.db.query(CollectiveIntentMembership).filter(CollectiveIntentMembership.id == commitment.membership_id).one()
        envelope = self.db.query(PrivateIntentEnvelope).filter(PrivateIntentEnvelope.id == membership.envelope_db_id).one()
        return private, round_row, offer, commitment, membership, envelope

    def _validate_current(self, user, private, round_row, offer, commitment, membership, envelope) -> None:
        if private.allocated_quantity <= 0 or private.status != "allocated":
            raise ValueError("only a positive allocated quantity can be accepted or rejected")
        if commitment.status != "active":
            raise ValueError("underlying conditional commitment is no longer active")
        if membership.status != "active":
            raise ValueError("collective membership is no longer active")
        if not CollectiveIntentService(self.db)._live_envelope(envelope):
            raise ValueError("private intent envelope is no longer live")
        if commitment.envelope_hash != envelope.envelope_hash:
            raise ValueError("private intent changed after conditional commitment")
        if private.requested_quantity != commitment.quantity:
            raise ValueError("allocation request quantity no longer matches commitment")

        effective = CollectiveAllocationService(self.db).effective_public_allocation(offer)
        if not effective["allocation_current"]:
            raise ValueError("collective allocation is no longer current")
        public_round = effective["allocation"]
        if public_round["allocation_id"] != round_row.allocation_id:
            raise ValueError("private allocation belongs to a superseded allocation round")
        if public_round["allocation_set_hash"] != round_row.allocation_set_hash:
            raise ValueError("allocation set hash mismatch")
        if public_round["commitment_set_hash"] != round_row.commitment_set_hash:
            raise ValueError("commitment set changed after allocation")

        evaluation = CollectiveOfferService(self.db).evaluate_for_user(user, membership, offer)
        if not evaluation.provisional_eligible:
            raise ValueError("fresh private agent evaluation no longer supports this offer")

        total_amount = round(float(offer.payload["unit_price"]) * int(private.allocated_quantity), 6)
        if total_amount > float(envelope.disclosure["budget_max"]):
            raise ValueError("allocated total now exceeds private budget ceiling")

    def decide(self, user: User, allocation_entry_id: str, decision: str, confirm: str) -> CollectiveAllocationDecision:
        if decision not in {"accepted", "rejected"}:
            raise ValueError("unsupported allocation decision")
        private, round_row, offer, commitment, membership, envelope = self._context(user, allocation_entry_id)
        self._validate_current(user, private, round_row, offer, commitment, membership, envelope)
        verb = "ACCEPT" if decision == "accepted" else "REJECT"
        required = f"{verb} ALLOCATION {private.allocation_entry_id} {private.allocated_quantity} {round_row.allocation_set_hash[-12:]}"
        if confirm != required:
            raise ValueError(f"confirmation must equal: {required}")

        existing = self.db.query(CollectiveAllocationDecision).filter(CollectiveAllocationDecision.private_allocation_id == private.id).one_or_none()
        unit_price = round(float(offer.payload["unit_price"]), 6)
        total_amount = round(unit_price * int(private.allocated_quantity), 6)
        decision_payload = {
            "protocol": "hae-post-allocation-acceptance-v1",
            "decision": decision,
            "allocation_id": round_row.allocation_id,
            "allocation_set_hash": round_row.allocation_set_hash,
            "allocation_entry_id": private.allocation_entry_id,
            "offer_hash": offer.offer_hash,
            "conditions_hash": commitment.conditions_hash,
            "envelope_hash": envelope.envelope_hash,
            "allocated_quantity": int(private.allocated_quantity),
            "unit_price": unit_price,
            "currency": offer.payload["currency"],
            "exact_total_amount": total_amount,
        }
        decision_hash = sha256_dict(decision_payload)
        if existing:
            if existing.decision == decision and existing.decision_hash == decision_hash and existing.revoked_at is None:
                return existing
            raise ValueError("this exact allocation already has a different or revoked decision")

        row = CollectiveAllocationDecision(
            user_id=user.id,
            private_allocation_id=private.id,
            commitment_id=commitment.id,
            decision_id=uuid.uuid4().hex,
            decision=decision,
            allocation_set_hash=round_row.allocation_set_hash,
            offer_hash=offer.offer_hash,
            conditions_hash=commitment.conditions_hash,
            envelope_hash=envelope.envelope_hash,
            allocated_quantity=private.allocated_quantity,
            unit_price=unit_price,
            currency=offer.payload["currency"],
            exact_total_amount=total_amount,
            decision_hash=decision_hash,
        )
        self.db.add(row)
        self.db.flush()
        if decision == "rejected":
            commitment.status = "revoked"
            commitment.revoked_at = datetime.utcnow()
        WorldModelService(self.db).append_event(
            user,
            EventCreate(
                event_type=f"collective.allocation_{decision}",
                source="user",
                subject_type="collective_allocation_decision",
                subject_id=row.decision_id,
                payload={
                    "offer_id": offer.offer_id,
                    "allocation_id": round_row.allocation_id,
                    "allocated_quantity": row.allocated_quantity,
                    "unit_price": row.unit_price,
                    "currency": row.currency,
                    "exact_total_amount": row.exact_total_amount,
                    "decision_hash": row.decision_hash,
                    "shared_with_responder": False,
                    "payment_created": False,
                    "order_created": False,
                },
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def revoke_acceptance(self, user: User, decision: CollectiveAllocationDecision, confirm: str) -> CollectiveAllocationDecision:
        if decision.user_id != user.id:
            raise ValueError("allocation decision does not belong to user")
        if decision.decision != "accepted":
            raise ValueError("only an accepted allocation can be revoked")
        if decision.revoked_at is not None:
            return decision
        required = f"REVOKE ALLOCATION ACCEPTANCE {decision.decision_id}"
        if confirm != required:
            raise ValueError(f"confirmation must equal: {required}")
        commitment = self.db.query(CollectiveConditionalCommitment).filter(CollectiveConditionalCommitment.id == decision.commitment_id).one()
        decision.revoked_at = datetime.utcnow()
        if commitment.status == "active":
            commitment.status = "revoked"
            commitment.revoked_at = datetime.utcnow()
        WorldModelService(self.db).append_event(
            user,
            EventCreate(
                event_type="collective.allocation_acceptance_revoked",
                source="user",
                subject_type="collective_allocation_decision",
                subject_id=decision.decision_id,
                payload={"shared_with_responder": False, "payment_created": False, "order_created": False},
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(decision)
        return decision
