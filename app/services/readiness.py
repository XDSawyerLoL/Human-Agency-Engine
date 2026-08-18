from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from ..adapter_models import AdapterPreflight, ExecutionAdapterManifest
from ..delegation_models import DelegationGrant
from ..execution_models import ExecutionDryRun, HumanCommitAuthorization
from ..models import PersonalMandate, User
from ..readiness_models import ExecutionReadinessReceipt
from ..sandbox_models import AdapterSandboxAttestation
from ..synthesis_models import CandidateIntervention
from ..world_schemas import EventCreate
from .policy import PolicyKernel, action_fingerprint
from .sandbox import SandboxAttestationService
from .world_model import WorldModelService


class ExecutionReadinessService:
    def __init__(self, db: Session):
        self.db = db

    def assess(self, preflight_public_id: str) -> ExecutionReadinessReceipt:
        preflight = (
            self.db.query(AdapterPreflight)
            .filter(AdapterPreflight.preflight_id == preflight_public_id)
            .one_or_none()
        )
        if not preflight:
            raise ValueError("adapter preflight not found")

        user = self.db.query(User).filter(User.id == preflight.user_id).one_or_none()
        dry_run = self.db.query(ExecutionDryRun).filter(ExecutionDryRun.id == preflight.dry_run_id).one_or_none()
        manifest = (
            self.db.query(ExecutionAdapterManifest)
            .filter(ExecutionAdapterManifest.id == preflight.adapter_manifest_id)
            .one_or_none()
        )
        candidate = (
            self.db.query(CandidateIntervention)
            .filter(CandidateIntervention.id == preflight.dry_run_id * 0 + preflight.user_id * 0 + (dry_run.candidate_id if dry_run else -1))
            .one_or_none()
            if dry_run
            else None
        )
        reasons: list[str] = []
        now = datetime.utcnow()

        if not user:
            raise ValueError("preflight user no longer exists")
        if not dry_run:
            reasons.append("dual-key dry-run no longer exists")
        if not manifest:
            reasons.append("adapter manifest no longer exists")
        if preflight.status != "contract_compatible":
            reasons.append("adapter preflight is not contract compatible")
        if preflight.external_probe_performed or preflight.external_dispatch:
            reasons.append("preflight contains forbidden external activity")

        if dry_run:
            if dry_run.status != "authorized_dry_run":
                reasons.append("dual-key dry-run is no longer authorized")
            if dry_run.would_execute or dry_run.external_dispatch:
                reasons.append("dual-key dry-run contains forbidden execution state")
        if manifest:
            if manifest.status != "active":
                reasons.append("adapter manifest is not active")
            if manifest.external_dispatch_enabled:
                reasons.append("adapter manifest has forbidden dispatch enabled")
            if preflight.adapter_contract_hash != manifest.contract_hash:
                reasons.append("preflight adapter contract hash is stale")

        if dry_run and candidate:
            current_fingerprint = action_fingerprint(candidate)
            if current_fingerprint != preflight.action_fingerprint:
                reasons.append("candidate action changed after adapter preflight")
            if current_fingerprint != dry_run.action_fingerprint:
                reasons.append("candidate action changed after dual-key dry-run")
        else:
            current_fingerprint = preflight.action_fingerprint
            if dry_run and not candidate:
                reasons.append("candidate no longer exists")

        grant = None
        human_commit = None
        if dry_run:
            grant = self.db.query(DelegationGrant).filter(DelegationGrant.id == dry_run.grant_id).one_or_none()
            human_commit = (
                self.db.query(HumanCommitAuthorization)
                .filter(HumanCommitAuthorization.id == dry_run.human_commit_id)
                .one_or_none()
            )
        if not grant:
            reasons.append("delegation grant no longer exists")
        else:
            if grant.capability != "execute_reversible":
                reasons.append("delegation capability is not execute_reversible")
            if grant.revoked_at is not None:
                reasons.append("delegation grant is revoked")
            if grant.expires_at <= now:
                reasons.append("delegation grant is expired")
            if grant.use_count >= grant.max_uses:
                reasons.append("delegation grant is exhausted")
            if grant.action_fingerprint != current_fingerprint:
                reasons.append("delegation action fingerprint is stale")
        if not human_commit:
            reasons.append("human commit no longer exists")
        else:
            if human_commit.status != "confirmed":
                reasons.append("human commit is not active")
            if human_commit.expires_at <= now:
                reasons.append("human commit is expired")
            if human_commit.action_fingerprint != current_fingerprint:
                reasons.append("human commit action fingerprint is stale")
            if not human_commit.rollback_plan.strip():
                reasons.append("human commit rollback plan is missing")

        mandate = (
            self.db.query(PersonalMandate)
            .filter(PersonalMandate.user_id == user.id)
            .one_or_none()
        )
        if not mandate:
            reasons.append("Personal Mandate no longer exists")
        elif grant and mandate.version != grant.mandate_version:
            reasons.append("Personal Mandate changed after delegation")
        if mandate and human_commit and mandate.version != human_commit.mandate_version:
            reasons.append("Personal Mandate changed after human commit")

        attestation: AdapterSandboxAttestation | None = None
        if manifest:
            attestation = SandboxAttestationService(self.db).effective_for_manifest(manifest)
        if not attestation:
            reasons.append("no effective sandbox attestation for exact adapter contract")
        elif attestation.adapter_contract_hash != preflight.adapter_contract_hash:
            reasons.append("sandbox attestation does not match preflight adapter contract")

        policy_receipt = None
        if candidate and grant and manifest:
            policy_receipt = PolicyKernel(self.db).evaluate(
                user,
                candidate,
                capability="execute_reversible",
                audience=manifest.audience,
                requested_constraints=grant.constraints,
            )
            if policy_receipt.decision != "allow":
                reasons.append("current Policy Kernel denied execution readiness")

        decision = "ready_for_controlled_integration" if not reasons else "blocked"
        checks = {
            "dual_key_dry_run_authorized": bool(
                dry_run
                and dry_run.status == "authorized_dry_run"
                and not dry_run.would_execute
                and not dry_run.external_dispatch
            ),
            "adapter_preflight_compatible": preflight.status == "contract_compatible",
            "adapter_contract_current": bool(
                manifest and preflight.adapter_contract_hash == manifest.contract_hash
            ),
            "human_commit_active": bool(
                human_commit and human_commit.status == "confirmed" and human_commit.expires_at > now
            ),
            "delegation_active": bool(
                grant
                and grant.revoked_at is None
                and grant.expires_at > now
                and grant.use_count < grant.max_uses
            ),
            "sandbox_attestation_effective": attestation is not None,
            "current_policy_allow": bool(policy_receipt and policy_receipt.decision == "allow"),
            "external_dispatch_enabled": False,
        }
        receipt = ExecutionReadinessReceipt(
            user_id=user.id,
            candidate_id=candidate.id if candidate else (dry_run.candidate_id if dry_run else 0),
            preflight_id=preflight.id,
            attestation_id=attestation.id if attestation else None,
            policy_receipt_id=policy_receipt.id if policy_receipt else None,
            receipt_id=uuid.uuid4().hex,
            mandate_version=mandate.version if mandate else 0,
            action_fingerprint=current_fingerprint,
            adapter_contract_hash=manifest.contract_hash if manifest else preflight.adapter_contract_hash,
            attestation_evidence_hash=attestation.evidence_hash if attestation else "",
            decision=decision,
            reasons=reasons,
            checks=checks,
            external_dispatch_enabled=False,
        )
        self.db.add(receipt)
        self.db.flush()
        WorldModelService(self.db).append_event(
            user,
            EventCreate(
                event_type="execution.readiness_assessed",
                source="readiness_gate",
                subject_type="execution_readiness_receipt",
                subject_id=receipt.receipt_id,
                payload={
                    "candidate_id": receipt.candidate_id,
                    "preflight_id": preflight.preflight_id,
                    "decision": decision,
                    "adapter_contract_hash": receipt.adapter_contract_hash,
                    "sandbox_attested": attestation is not None,
                    "external_dispatch_enabled": False,
                },
                correlation_id=f"candidate:{receipt.candidate_id}",
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(receipt)
        return receipt
