from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..delegation_models import DelegationGrant
from ..execution_models import ExecutionDryRun, HumanCommitAuthorization, PolicyReceipt
from ..execution_schemas import DualKeyDryRunRequest, HumanCommitPrepare
from ..models import PersonalMandate, User
from ..synthesis_models import CandidateIntervention
from ..world_schemas import EventCreate
from .delegation import DelegationService
from .policy import PolicyKernel, action_fingerprint, minimal_intervention, sha256_text
from .world_model import WorldModelService


def _token_hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


class HumanCommitService:
    def __init__(self, db: Session):
        self.db = db

    def prepare(self, user: User, request: HumanCommitPrepare) -> HumanCommitAuthorization:
        required = f"PREPARE COMMIT {request.candidate_id}"
        if request.confirm != required:
            raise ValueError(f"confirmation must equal: {required}")
        if request.audience.strip() in {"", "*"}:
            raise ValueError("human commit requires a specific audience")

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

        receipt = PolicyKernel(self.db).evaluate(
            user,
            candidate,
            capability="execute_reversible",
            audience=request.audience,
        )
        if receipt.decision != "allow":
            self.db.commit()
            raise ValueError("policy kernel denied commit: " + "; ".join(receipt.reasons))

        mandate = (
            self.db.query(PersonalMandate)
            .filter(PersonalMandate.user_id == user.id)
            .one_or_none()
        )
        if not mandate:
            self.db.commit()
            raise ValueError("Personal Mandate must be configured before commit")

        exact_action = minimal_intervention(candidate)
        fingerprint = action_fingerprint(candidate)
        rollback_plan = request.rollback_plan.strip()
        if not rollback_plan:
            self.db.commit()
            raise ValueError("rollback plan is required")

        now = datetime.utcnow()
        commit = HumanCommitAuthorization(
            user_id=user.id,
            candidate_id=candidate.id,
            policy_receipt_id=receipt.id,
            commit_id=uuid.uuid4().hex,
            audience=request.audience,
            mandate_version=mandate.version,
            action_type=str(exact_action.get("type", ""))[:96],
            action_fingerprint=fingerprint,
            exact_action=exact_action,
            rollback_plan=rollback_plan,
            rollback_fingerprint=sha256_text(rollback_plan),
            status="prepared",
            prepared_at=now,
            expires_at=now + timedelta(seconds=request.expires_in_seconds),
        )
        self.db.add(commit)
        self.db.flush()
        WorldModelService(self.db).append_event(
            user,
            EventCreate(
                event_type="execution.human_commit_prepared",
                source="user",
                subject_type="human_commit",
                subject_id=commit.commit_id,
                payload={
                    "candidate_id": candidate.id,
                    "audience": commit.audience,
                    "action_fingerprint": commit.action_fingerprint,
                    "policy_receipt_hash": receipt.receipt_hash,
                    "expires_at": commit.expires_at.isoformat(),
                },
                correlation_id=f"candidate:{candidate.id}",
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(commit)
        return commit

    def confirm(self, user: User, commit_id: str, confirm: str) -> tuple[HumanCommitAuthorization, str]:
        commit = (
            self.db.query(HumanCommitAuthorization)
            .filter(
                HumanCommitAuthorization.commit_id == commit_id,
                HumanCommitAuthorization.user_id == user.id,
            )
            .with_for_update()
            .one_or_none()
        )
        if not commit:
            raise ValueError("human commit not found for user")
        if commit.status != "prepared":
            raise ValueError("human commit is not awaiting confirmation")
        if commit.expires_at <= datetime.utcnow():
            commit.status = "expired"
            self.db.commit()
            raise ValueError("human commit expired before confirmation")

        required = f"COMMIT {commit.commit_id} {commit.action_fingerprint[-12:]}"
        if confirm != required:
            raise ValueError(f"confirmation must equal: {required}")

        mandate = (
            self.db.query(PersonalMandate)
            .filter(PersonalMandate.user_id == user.id)
            .one_or_none()
        )
        if not mandate or mandate.version != commit.mandate_version:
            raise ValueError("human commit is stale because Personal Mandate changed")

        candidate = (
            self.db.query(CandidateIntervention)
            .filter(CandidateIntervention.id == commit.candidate_id)
            .one_or_none()
        )
        if not candidate or action_fingerprint(candidate) != commit.action_fingerprint:
            raise ValueError("human commit is stale because exact action changed")

        token = secrets.token_urlsafe(48)
        commit.token_hash = _token_hash(token)
        commit.status = "confirmed"
        commit.confirmed_at = datetime.utcnow()
        WorldModelService(self.db).append_event(
            user,
            EventCreate(
                event_type="execution.human_commit_confirmed",
                source="user",
                subject_type="human_commit",
                subject_id=commit.commit_id,
                payload={
                    "candidate_id": commit.candidate_id,
                    "audience": commit.audience,
                    "action_fingerprint": commit.action_fingerprint,
                },
                correlation_id=f"candidate:{commit.candidate_id}",
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(commit)
        return commit, token

    def revoke(self, user: User, commit_id: str) -> HumanCommitAuthorization:
        commit = (
            self.db.query(HumanCommitAuthorization)
            .filter(
                HumanCommitAuthorization.commit_id == commit_id,
                HumanCommitAuthorization.user_id == user.id,
            )
            .one_or_none()
        )
        if not commit:
            raise ValueError("human commit not found for user")
        if commit.status not in {"consumed", "expired", "revoked"}:
            commit.status = "revoked"
            commit.revoked_at = datetime.utcnow()
            commit.token_hash = None
            self.db.commit()
            self.db.refresh(commit)
        return commit


class DualKeyExecutionGateway:
    def __init__(self, db: Session):
        self.db = db

    def dry_run(self, request: DualKeyDryRunRequest) -> ExecutionDryRun:
        existing = (
            self.db.query(ExecutionDryRun)
            .filter(ExecutionDryRun.request_id == request.request_id)
            .one_or_none()
        )
        if existing:
            raise ValueError("dry-run request_id has already been used")

        verified = DelegationService(self.db).verify(
            request.delegation_token,
            audience=request.audience,
        )
        grant: DelegationGrant = verified["grant"]
        claims = verified["claims"]
        if grant.capability != "execute_reversible":
            raise ValueError("dual-key gateway requires execute_reversible delegation")
        if grant.action_fingerprint != request.action_fingerprint:
            raise ValueError("delegation action fingerprint does not match requested dry-run")

        commit_hash = _token_hash(request.human_commit_token)
        human_commit = (
            self.db.query(HumanCommitAuthorization)
            .filter(HumanCommitAuthorization.token_hash == commit_hash)
            .with_for_update()
            .one_or_none()
        )
        if not human_commit:
            raise ValueError("human commit capability is unknown")
        if human_commit.status != "confirmed":
            raise ValueError("human commit is not active")
        if human_commit.expires_at <= datetime.utcnow():
            human_commit.status = "expired"
            human_commit.token_hash = None
            self.db.commit()
            raise ValueError("human commit expired")

        if human_commit.user_id != grant.user_id:
            raise ValueError("delegation and human commit belong to different users")
        if human_commit.candidate_id != grant.candidate_id:
            raise ValueError("delegation and human commit reference different candidates")
        if human_commit.audience != request.audience or grant.audience != request.audience:
            raise ValueError("delegation and human commit audience mismatch")
        if human_commit.mandate_version != grant.mandate_version:
            raise ValueError("delegation and human commit mandate versions differ")
        if human_commit.action_fingerprint != request.action_fingerprint:
            raise ValueError("human commit action fingerprint does not match requested dry-run")
        if claims.get("action", {}).get("fingerprint") != request.action_fingerprint:
            raise ValueError("signed delegation action differs from requested dry-run")

        user = self.db.query(User).filter(User.id == grant.user_id).one()
        candidate = (
            self.db.query(CandidateIntervention)
            .filter(
                CandidateIntervention.id == grant.candidate_id,
                CandidateIntervention.user_id == user.id,
            )
            .one_or_none()
        )
        if not candidate:
            raise ValueError("candidate no longer exists")
        if action_fingerprint(candidate) != request.action_fingerprint:
            raise ValueError("candidate action changed after authorization")
        if minimal_intervention(candidate).get("reversible") is not True:
            raise ValueError("candidate is no longer explicitly reversible")
        if not human_commit.rollback_plan.strip():
            raise ValueError("human commit does not contain a rollback plan")

        current_policy = PolicyKernel(self.db).evaluate(
            user,
            candidate,
            capability="execute_reversible",
            audience=request.audience,
            requested_constraints=grant.constraints,
        )
        if current_policy.decision != "allow":
            self.db.commit()
            raise ValueError("current policy kernel denied dry-run: " + "; ".join(current_policy.reasons))

        original_policy = (
            self.db.query(PolicyReceipt)
            .filter(PolicyReceipt.id == human_commit.policy_receipt_id)
            .one_or_none()
        )
        if not original_policy or original_policy.decision != "allow":
            raise ValueError("human commit is not backed by an allow policy receipt")
        if original_policy.action_fingerprint != request.action_fingerprint:
            raise ValueError("human commit policy receipt action mismatch")

        checks = {
            "delegation_signature_valid": True,
            "delegation_capability": "execute_reversible",
            "human_commit_valid": True,
            "same_user": True,
            "same_candidate": True,
            "same_audience": True,
            "same_mandate_version": True,
            "same_action_fingerprint": True,
            "reversible": True,
            "rollback_plan_present": True,
            "current_policy_decision": current_policy.decision,
            "external_dispatch_enabled": False,
        }
        dry_run = ExecutionDryRun(
            user_id=user.id,
            candidate_id=candidate.id,
            grant_id=grant.id,
            human_commit_id=human_commit.id,
            request_id=request.request_id,
            audience=request.audience,
            action_fingerprint=request.action_fingerprint,
            checks=checks,
            status="authorized_dry_run",
            would_execute=False,
            external_dispatch=False,
        )
        self.db.add(dry_run)
        self.db.flush()
        WorldModelService(self.db).append_event(
            user,
            EventCreate(
                event_type="execution.dual_key_dry_run_authorized",
                source="execution_gateway",
                subject_type="execution_dry_run",
                subject_id=request.request_id,
                payload={
                    "candidate_id": candidate.id,
                    "grant_id": grant.grant_id,
                    "human_commit_id": human_commit.commit_id,
                    "audience": request.audience,
                    "action_fingerprint": request.action_fingerprint,
                    "external_dispatch": False,
                    "would_execute": False,
                },
                correlation_id=f"candidate:{candidate.id}",
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(dry_run)
        return dry_run
