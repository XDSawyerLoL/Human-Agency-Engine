from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from ..acquisition_models import InformationNeed
from ..execution_models import PolicyReceipt
from ..models import PersonalMandate, User
from ..synthesis_models import CandidateIntervention

POLICY_ENGINE_VERSION = "hae-policy-kernel-v1"
ALLOWED_CAPABILITIES = {"inspect", "prepare", "execute_reversible"}


def canonical_json(value: dict) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_dict(value: dict) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def minimal_intervention(candidate: CandidateIntervention) -> dict:
    intervention = dict(candidate.intervention or {})
    intervention.pop("_candidate_id", None)
    return intervention


def action_fingerprint(candidate: CandidateIntervention) -> str:
    return sha256_dict(minimal_intervention(candidate))


class PolicyKernel:
    def __init__(self, db: Session):
        self.db = db

    def evaluate(
        self,
        user: User,
        candidate: CandidateIntervention,
        *,
        capability: str,
        audience: str,
        requested_constraints: dict | None = None,
    ) -> PolicyReceipt:
        requested_constraints = dict(requested_constraints or {})
        reasons: list[str] = []

        mandate = (
            self.db.query(PersonalMandate)
            .filter(PersonalMandate.user_id == user.id)
            .one_or_none()
        )
        if not mandate:
            reasons.append("personal mandate is not configured")

        if candidate.user_id != user.id:
            reasons.append("candidate does not belong to user")
        if candidate.status != "ready_for_review":
            reasons.append("candidate has not passed CARE + FUTURE + Decision Lab")
        if capability not in ALLOWED_CAPABILITIES:
            reasons.append("capability is not recognized by the policy kernel")
        if audience.strip() in {"", "*"}:
            reasons.append("audience must be specific")

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
            reasons.append("candidate still has blocking information needs")

        intervention = minimal_intervention(candidate)
        action_type = str(intervention.get("type", ""))

        if mandate:
            mandate_constraints = dict(mandate.constraints or {})
            forbidden_action_types = mandate_constraints.get("forbidden_action_types", [])
            if isinstance(forbidden_action_types, list) and action_type in forbidden_action_types:
                reasons.append("action type is forbidden by personal mandate")

            forbidden_categories = mandate_constraints.get("forbidden_categories", [])
            requested_category = requested_constraints.get("category")
            if (
                requested_category
                and isinstance(forbidden_categories, list)
                and requested_category in forbidden_categories
            ):
                reasons.append("requested category is forbidden by personal mandate")

            mandate_max_amount = mandate_constraints.get("max_transaction_amount")
            requested_max_amount = requested_constraints.get("max_amount")
            if isinstance(mandate_max_amount, (int, float)) and isinstance(requested_max_amount, (int, float)):
                if requested_max_amount > mandate_max_amount:
                    reasons.append("requested amount exceeds personal mandate transaction ceiling")

            if capability == "execute_reversible":
                if intervention.get("reversible") is not True:
                    reasons.append("execution capability requires an explicitly reversible intervention")
                if not bool((mandate.autonomy or {}).get("allow_execute_reversible", False)):
                    reasons.append("personal mandate does not allow reversible execution")

        decision = "allow" if not reasons else "deny"
        receipt_id = uuid.uuid4().hex
        fingerprint = action_fingerprint(candidate)
        payload = {
            "receipt_id": receipt_id,
            "engine_version": POLICY_ENGINE_VERSION,
            "user_id": user.id,
            "candidate_id": candidate.id,
            "mandate_version": mandate.version if mandate else 0,
            "capability": capability,
            "audience": audience,
            "action_fingerprint": fingerprint,
            "decision": decision,
            "reasons": reasons,
            "requested_constraints": requested_constraints,
            "evaluated_at": datetime.utcnow().isoformat(timespec="microseconds"),
        }
        receipt = PolicyReceipt(
            user_id=user.id,
            candidate_id=candidate.id,
            receipt_id=receipt_id,
            engine_version=POLICY_ENGINE_VERSION,
            mandate_version=mandate.version if mandate else 0,
            capability=capability,
            audience=audience,
            action_fingerprint=fingerprint,
            decision=decision,
            reasons=reasons,
            evaluated_constraints=requested_constraints,
            receipt_hash=sha256_dict(payload),
        )
        self.db.add(receipt)
        self.db.flush()
        return receipt
