from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from ..adapter_models import AdapterPreflight, ExecutionAdapterManifest
from ..adapter_schemas import AdapterManifestRegister, AdapterPreflightRequest
from ..delegation_models import DelegationGrant
from ..execution_models import ExecutionDryRun, HumanCommitAuthorization
from ..models import PersonalMandate, User
from ..synthesis_models import CandidateIntervention
from ..world_schemas import EventCreate
from .policy import PolicyKernel, action_fingerprint, minimal_intervention, sha256_dict
from .world_model import WorldModelService


def _manifest_payload(request: AdapterManifestRegister) -> dict:
    return {
        "adapter_id": request.adapter_id.strip(),
        "version": request.version.strip(),
        "audience": request.audience.strip(),
        "supported_action_types": sorted(set(request.supported_action_types)),
        "reversible_only": request.reversible_only,
        "supports_idempotency": request.supports_idempotency,
        "supports_rollback": request.supports_rollback,
        "side_effect_free_preflight": request.side_effect_free_preflight,
        "external_dispatch_enabled": request.external_dispatch_enabled,
    }


def _stored_manifest_payload(manifest: ExecutionAdapterManifest) -> dict:
    return {
        "adapter_id": manifest.adapter_id,
        "version": manifest.version,
        "audience": manifest.audience,
        "supported_action_types": sorted(set(manifest.supported_action_types or [])),
        "reversible_only": manifest.reversible_only,
        "supports_idempotency": manifest.supports_idempotency,
        "supports_rollback": manifest.supports_rollback,
        "side_effect_free_preflight": manifest.side_effect_free_preflight,
        "external_dispatch_enabled": manifest.external_dispatch_enabled,
    }


class AdapterRegistry:
    def __init__(self, db: Session):
        self.db = db

    def register(self, request: AdapterManifestRegister) -> ExecutionAdapterManifest:
        payload = _manifest_payload(request)
        required = f"REGISTER ADAPTER {payload['adapter_id']} {payload['version']}"
        if request.confirm != required:
            raise ValueError(f"confirmation must equal: {required}")
        if payload["audience"] in {"", "*"}:
            raise ValueError("adapter audience must be specific")
        if not payload["supported_action_types"]:
            raise ValueError("adapter must declare at least one supported action type")
        if any(not isinstance(item, str) or not item.strip() for item in payload["supported_action_types"]):
            raise ValueError("supported action types must be non-empty strings")

        # V1 registry accepts only manifests that are safe for local preflight.
        if payload["reversible_only"] is not True:
            raise ValueError("V1 adapters must be reversible_only")
        if payload["supports_idempotency"] is not True:
            raise ValueError("V1 adapters must support idempotency")
        if payload["supports_rollback"] is not True:
            raise ValueError("V1 adapters must support rollback")
        if payload["side_effect_free_preflight"] is not True:
            raise ValueError("V1 adapters must guarantee side-effect-free preflight")
        if payload["external_dispatch_enabled"] is not False:
            raise ValueError("external dispatch cannot be enabled in adapter contract V1")

        contract_hash = sha256_dict(payload)
        existing = (
            self.db.query(ExecutionAdapterManifest)
            .filter(
                ExecutionAdapterManifest.adapter_id == payload["adapter_id"],
                ExecutionAdapterManifest.version == payload["version"],
            )
            .one_or_none()
        )
        if existing:
            if existing.contract_hash != contract_hash:
                raise ValueError("adapter version is immutable and already has a different contract")
            return existing

        manifest = ExecutionAdapterManifest(
            adapter_id=payload["adapter_id"],
            version=payload["version"],
            audience=payload["audience"],
            supported_action_types=payload["supported_action_types"],
            reversible_only=True,
            supports_idempotency=True,
            supports_rollback=True,
            side_effect_free_preflight=True,
            external_dispatch_enabled=False,
            status="active",
            contract_hash=contract_hash,
        )
        self.db.add(manifest)
        self.db.commit()
        self.db.refresh(manifest)
        return manifest


class AdapterPreflightService:
    def __init__(self, db: Session):
        self.db = db

    def run(self, request: AdapterPreflightRequest) -> AdapterPreflight:
        manifest = (
            self.db.query(ExecutionAdapterManifest)
            .filter(
                ExecutionAdapterManifest.adapter_id == request.adapter_id,
                ExecutionAdapterManifest.version == request.version,
            )
            .one_or_none()
        )
        if not manifest:
            raise ValueError("adapter manifest not found")

        existing = (
            self.db.query(AdapterPreflight)
            .filter(
                AdapterPreflight.adapter_manifest_id == manifest.id,
                AdapterPreflight.idempotency_key == request.idempotency_key,
            )
            .one_or_none()
        )

        dry_run = (
            self.db.query(ExecutionDryRun)
            .filter(ExecutionDryRun.request_id == request.dry_run_request_id)
            .one_or_none()
        )
        if not dry_run:
            raise ValueError("authorized execution dry-run not found")
        if existing:
            if existing.dry_run_id != dry_run.id:
                raise ValueError("idempotency key is already bound to a different dry-run")
            return existing

        if manifest.status != "active":
            raise ValueError("adapter manifest is not active")
        if manifest.external_dispatch_enabled:
            raise ValueError("adapter external dispatch must remain disabled in V1")
        if not all(
            (
                manifest.reversible_only,
                manifest.supports_idempotency,
                manifest.supports_rollback,
                manifest.side_effect_free_preflight,
            )
        ):
            raise ValueError("adapter manifest no longer satisfies V1 safety contract")
        if sha256_dict(_stored_manifest_payload(manifest)) != manifest.contract_hash:
            raise ValueError("adapter manifest contract hash mismatch")

        if dry_run.status != "authorized_dry_run":
            raise ValueError("execution dry-run is not authorized")
        if dry_run.would_execute or dry_run.external_dispatch:
            raise ValueError("preflight accepts only non-executing dry-runs")

        user = self.db.query(User).filter(User.id == dry_run.user_id).one()
        candidate = (
            self.db.query(CandidateIntervention)
            .filter(
                CandidateIntervention.id == dry_run.candidate_id,
                CandidateIntervention.user_id == user.id,
            )
            .one_or_none()
        )
        if not candidate:
            raise ValueError("candidate no longer exists")
        intervention = minimal_intervention(candidate)
        current_fingerprint = action_fingerprint(candidate)
        action_type = str(intervention.get("type", ""))
        if current_fingerprint != dry_run.action_fingerprint:
            raise ValueError("candidate action changed after dry-run")
        if intervention.get("reversible") is not True:
            raise ValueError("candidate is no longer explicitly reversible")
        if action_type not in (manifest.supported_action_types or []):
            raise ValueError("adapter does not support this action type")
        if manifest.audience != dry_run.audience:
            raise ValueError("adapter audience does not match execution dry-run")

        human_commit = (
            self.db.query(HumanCommitAuthorization)
            .filter(HumanCommitAuthorization.id == dry_run.human_commit_id)
            .one_or_none()
        )
        if not human_commit or human_commit.status != "confirmed":
            raise ValueError("human commit is no longer active")
        if human_commit.expires_at <= datetime.utcnow():
            raise ValueError("human commit expired before adapter preflight")
        if human_commit.action_fingerprint != current_fingerprint:
            raise ValueError("human commit no longer matches candidate action")
        if not human_commit.rollback_plan.strip():
            raise ValueError("human commit rollback plan is missing")

        grant = (
            self.db.query(DelegationGrant)
            .filter(DelegationGrant.id == dry_run.grant_id)
            .one_or_none()
        )
        if not grant:
            raise ValueError("delegation grant no longer exists")
        if grant.capability != "execute_reversible":
            raise ValueError("adapter preflight requires execute_reversible delegation")
        if grant.revoked_at is not None:
            raise ValueError("delegation grant was revoked")
        if grant.expires_at <= datetime.utcnow():
            raise ValueError("delegation grant expired before adapter preflight")
        if grant.use_count >= grant.max_uses:
            raise ValueError("delegation grant is exhausted")
        if grant.audience != manifest.audience:
            raise ValueError("delegation audience does not match adapter")
        if grant.action_fingerprint != current_fingerprint:
            raise ValueError("delegation action no longer matches candidate")

        mandate = (
            self.db.query(PersonalMandate)
            .filter(PersonalMandate.user_id == user.id)
            .one_or_none()
        )
        if not mandate or mandate.version != grant.mandate_version:
            raise ValueError("Personal Mandate changed after dual-key authorization")
        if human_commit.mandate_version != mandate.version:
            raise ValueError("human commit is stale against current Personal Mandate")

        policy = PolicyKernel(self.db).evaluate(
            user,
            candidate,
            capability="execute_reversible",
            audience=manifest.audience,
            requested_constraints=grant.constraints,
        )
        if policy.decision != "allow":
            self.db.commit()
            raise ValueError("current policy kernel denied adapter preflight: " + "; ".join(policy.reasons))

        checks = {
            "authorized_dual_key_dry_run": True,
            "manifest_hash_valid": True,
            "manifest_immutable_version": True,
            "exact_audience_match": True,
            "action_type_supported": True,
            "exact_action_fingerprint_match": True,
            "reversible_only": True,
            "idempotency_required": True,
            "rollback_supported": True,
            "rollback_plan_present": True,
            "side_effect_free_preflight": True,
            "current_policy_decision": policy.decision,
            "external_probe_performed": False,
            "external_dispatch_enabled": False,
        }
        preflight = AdapterPreflight(
            user_id=user.id,
            dry_run_id=dry_run.id,
            adapter_manifest_id=manifest.id,
            preflight_id=uuid.uuid4().hex,
            idempotency_key=request.idempotency_key,
            audience=manifest.audience,
            action_type=action_type,
            action_fingerprint=current_fingerprint,
            adapter_contract_hash=manifest.contract_hash,
            rollback_fingerprint=human_commit.rollback_fingerprint,
            checks=checks,
            status="contract_compatible",
            external_probe_performed=False,
            external_dispatch=False,
        )
        self.db.add(preflight)
        self.db.flush()
        WorldModelService(self.db).append_event(
            user,
            EventCreate(
                event_type="execution.adapter_preflight_completed",
                source="adapter_preflight",
                subject_type="adapter_preflight",
                subject_id=preflight.preflight_id,
                payload={
                    "adapter_id": manifest.adapter_id,
                    "adapter_version": manifest.version,
                    "adapter_contract_hash": manifest.contract_hash,
                    "candidate_id": candidate.id,
                    "action_fingerprint": current_fingerprint,
                    "external_probe_performed": False,
                    "external_dispatch": False,
                },
                correlation_id=f"candidate:{candidate.id}",
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(preflight)
        return preflight
