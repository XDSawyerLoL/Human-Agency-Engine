from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import datetime, timedelta

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy.orm import Session

from ..adapter_models import ExecutionAdapterManifest
from ..sandbox_models import AdapterSandboxAttestation, SandboxRunnerIdentity
from ..sandbox_schemas import SandboxAttestationSubmit, SandboxEvidence, SandboxRunnerRegister
from .policy import canonical_json, sha256_dict

SANDBOX_SUITE_VERSION = "hae-adapter-sandbox-v1"
MAX_SIGNED_EVIDENCE_BYTES = 65536
MAX_EVIDENCE_AGE_SECONDS = 7 * 24 * 60 * 60
MAX_FUTURE_CLOCK_SKEW_SECONDS = 300


def _b64u_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _key_fingerprint(public_raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(public_raw).hexdigest()


def sandbox_signed_payload(
    manifest: ExecutionAdapterManifest,
    suite_version: str,
    evidence: SandboxEvidence | dict,
) -> dict:
    evidence_data = evidence.model_dump() if isinstance(evidence, SandboxEvidence) else dict(evidence)
    return {
        "protocol": "hae-sandbox-attestation-v1",
        "adapter": {
            "adapter_id": manifest.adapter_id,
            "version": manifest.version,
            "contract_hash": manifest.contract_hash,
        },
        "suite_version": suite_version,
        "evidence": evidence_data,
    }


class SandboxRunnerRegistry:
    def __init__(self, db: Session):
        self.db = db

    def register(self, request: SandboxRunnerRegister) -> SandboxRunnerIdentity:
        runner_id = request.runner_id.strip()
        required = f"TRUST SANDBOX RUNNER {runner_id}"
        if request.confirm != required:
            raise ValueError(f"confirmation must equal: {required}")
        try:
            public_raw = _b64u_decode(request.public_key_b64)
            if len(public_raw) != 32:
                raise ValueError("Ed25519 public key must be 32 bytes")
            Ed25519PublicKey.from_public_bytes(public_raw)
        except Exception as exc:
            if isinstance(exc, ValueError) and str(exc) == "Ed25519 public key must be 32 bytes":
                raise
            raise ValueError("invalid Ed25519 sandbox runner public key") from exc

        fingerprint = _key_fingerprint(public_raw)
        existing = (
            self.db.query(SandboxRunnerIdentity)
            .filter(SandboxRunnerIdentity.runner_id == runner_id)
            .one_or_none()
        )
        if existing:
            if existing.key_fingerprint != fingerprint:
                raise ValueError("sandbox runner identity is immutable; register a new runner_id for a new key")
            if existing.revoked_at is not None or existing.status != "active":
                raise ValueError("sandbox runner identity is revoked")
            return existing

        runner = SandboxRunnerIdentity(
            runner_id=runner_id,
            label=request.label.strip(),
            public_key_b64=request.public_key_b64,
            key_fingerprint=fingerprint,
            status="active",
        )
        self.db.add(runner)
        self.db.commit()
        self.db.refresh(runner)
        return runner

    def revoke(self, runner: SandboxRunnerIdentity, confirm: str) -> SandboxRunnerIdentity:
        required = f"REVOKE SANDBOX RUNNER {runner.runner_id}"
        if confirm != required:
            raise ValueError(f"confirmation must equal: {required}")
        if runner.revoked_at is None:
            runner.status = "revoked"
            runner.revoked_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(runner)
        return runner


class SandboxAttestationService:
    def __init__(self, db: Session):
        self.db = db

    def submit(self, request: SandboxAttestationSubmit) -> AdapterSandboxAttestation:
        if request.suite_version != SANDBOX_SUITE_VERSION:
            raise ValueError("unsupported sandbox suite version")

        manifest = (
            self.db.query(ExecutionAdapterManifest)
            .filter(
                ExecutionAdapterManifest.adapter_id == request.adapter_id,
                ExecutionAdapterManifest.version == request.version,
            )
            .one_or_none()
        )
        if not manifest or manifest.status != "active":
            raise ValueError("active adapter manifest not found")
        if manifest.external_dispatch_enabled:
            raise ValueError("sandbox attestation V1 does not accept dispatch-enabled adapters")

        runner = (
            self.db.query(SandboxRunnerIdentity)
            .filter(SandboxRunnerIdentity.runner_id == request.runner_id)
            .one_or_none()
        )
        if not runner or runner.status != "active" or runner.revoked_at is not None:
            raise ValueError("trusted active sandbox runner not found")

        now = datetime.utcnow()
        observed_at = datetime.utcfromtimestamp(request.evidence.observed_at_epoch)
        age_seconds = (now - observed_at).total_seconds()
        if age_seconds > MAX_EVIDENCE_AGE_SECONDS:
            raise ValueError("sandbox evidence is too old")
        if age_seconds < -MAX_FUTURE_CLOCK_SKEW_SECONDS:
            raise ValueError("sandbox evidence timestamp is too far in the future")

        signed_payload = sandbox_signed_payload(manifest, request.suite_version, request.evidence)
        signed_bytes = canonical_json(signed_payload)
        if len(signed_bytes) > MAX_SIGNED_EVIDENCE_BYTES:
            raise ValueError("sandbox evidence exceeds maximum signed payload size")

        try:
            signature = _b64u_decode(request.signature_b64)
            public_key = Ed25519PublicKey.from_public_bytes(_b64u_decode(runner.public_key_b64))
            public_key.verify(signature, signed_bytes)
        except (InvalidSignature, ValueError, TypeError) as exc:
            raise ValueError("invalid sandbox evidence signature") from exc

        evidence_hash = sha256_dict(signed_payload)
        existing = (
            self.db.query(AdapterSandboxAttestation)
            .filter(
                AdapterSandboxAttestation.runner_identity_id == runner.id,
                AdapterSandboxAttestation.runner_run_id == request.evidence.run_id,
            )
            .one_or_none()
        )
        if existing:
            if existing.evidence_hash != evidence_hash:
                raise ValueError("sandbox runner run_id replayed with different evidence")
            return existing

        evidence = request.evidence
        initial_state_hash = sha256_dict(evidence.initial_state)
        post_preflight_state_hash = sha256_dict(evidence.state_after_preflight)
        first_result_hash = sha256_dict(evidence.first_result)
        repeat_result_hash = sha256_dict(evidence.repeat_result)
        post_first_state_hash = sha256_dict(evidence.state_after_first)
        post_repeat_state_hash = sha256_dict(evidence.state_after_repeat)
        partial_failure_before_hash = sha256_dict(evidence.partial_failure_state_before)
        partial_failure_after_hash = sha256_dict(evidence.partial_failure_state_after)
        rollback_state_hash = sha256_dict(evidence.state_after_rollback)

        preflight_no_side_effect = initial_state_hash == post_preflight_state_hash
        idempotency_verified = (
            first_result_hash == repeat_result_hash
            and post_first_state_hash == post_repeat_state_hash
        )
        partial_failure_safe = partial_failure_before_hash == partial_failure_after_hash
        rollback_restored = initial_state_hash == rollback_state_hash
        passed = all(
            (
                preflight_no_side_effect,
                idempotency_verified,
                partial_failure_safe,
                rollback_restored,
            )
        )

        attestation = AdapterSandboxAttestation(
            adapter_manifest_id=manifest.id,
            runner_identity_id=runner.id,
            attestation_id=uuid.uuid4().hex,
            runner_run_id=evidence.run_id,
            suite_version=request.suite_version,
            adapter_contract_hash=manifest.contract_hash,
            evidence_hash=evidence_hash,
            signature_b64=request.signature_b64,
            initial_state_hash=initial_state_hash,
            post_preflight_state_hash=post_preflight_state_hash,
            first_result_hash=first_result_hash,
            repeat_result_hash=repeat_result_hash,
            post_first_state_hash=post_first_state_hash,
            post_repeat_state_hash=post_repeat_state_hash,
            partial_failure_before_hash=partial_failure_before_hash,
            partial_failure_after_hash=partial_failure_after_hash,
            rollback_state_hash=rollback_state_hash,
            preflight_no_side_effect=preflight_no_side_effect,
            idempotency_verified=idempotency_verified,
            partial_failure_safe=partial_failure_safe,
            rollback_restored=rollback_restored,
            status="passed" if passed else "failed",
            observed_at=observed_at,
            valid_until=(now + timedelta(seconds=request.valid_for_seconds)) if passed else now,
        )
        self.db.add(attestation)
        self.db.commit()
        self.db.refresh(attestation)
        return attestation

    def effective_for_manifest(self, manifest: ExecutionAdapterManifest) -> AdapterSandboxAttestation | None:
        now = datetime.utcnow()
        attestations = (
            self.db.query(AdapterSandboxAttestation)
            .filter(
                AdapterSandboxAttestation.adapter_manifest_id == manifest.id,
                AdapterSandboxAttestation.status == "passed",
                AdapterSandboxAttestation.valid_until > now,
                AdapterSandboxAttestation.adapter_contract_hash == manifest.contract_hash,
            )
            .order_by(AdapterSandboxAttestation.created_at.desc())
            .all()
        )
        for attestation in attestations:
            runner = (
                self.db.query(SandboxRunnerIdentity)
                .filter(SandboxRunnerIdentity.id == attestation.runner_identity_id)
                .one_or_none()
            )
            if runner and runner.status == "active" and runner.revoked_at is None:
                return attestation
        return None
