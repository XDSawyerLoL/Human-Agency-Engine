from __future__ import annotations

import hashlib
import posixpath
import uuid
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ..adapter_models import AdapterPreflight, ExecutionAdapterManifest
from ..adapter_schemas import AdapterManifestRegister
from ..config import settings
from ..models import User
from ..software_agent_models import SoftwareAgentRun
from ..software_agent_schemas import SoftwareAgentLaunchRequest
from ..world_schemas import EventCreate
from .adapters import AdapterRegistry
from .sandbox import SandboxAttestationService
from .world_model import WorldModelService


SOFTWARE_AGENT_ADAPTER_ID = "aura-software-engine"
SOFTWARE_AGENT_ADAPTER_VERSION = "1.0.0"
SOFTWARE_AGENT_AUDIENCE = "aura-software-sandbox"
SOFTWARE_AGENT_ACTION_TYPE = "software_patch"
SOFTWARE_AGENT_PROVIDER = "openhands-agent-server"
_TERMINAL_EXECUTION_STATES = {"finished", "error", "stuck"}


def _sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _allowed_repositories() -> set[str]:
    return {
        item.strip().lower()
        for item in settings.software_agent_allowed_repositories.split(",")
        if item.strip()
    }


class SoftwareAgentSandboxService:
    """AURA software-engine bridge to an isolated OpenHands Agent Server.

    The bridge launches only sandbox-local worktree conversations. It never
    pushes a branch, merges a pull request or performs production deployment.
    Promotion remains a separate branch-test-canary-promote decision.
    """

    def __init__(self, db: Session):
        self.db = db

    def bootstrap(self, confirm: str) -> ExecutionAdapterManifest:
        if confirm != "REGISTER AURA SOFTWARE ENGINE":
            raise ValueError("confirmation must equal: REGISTER AURA SOFTWARE ENGINE")
        return AdapterRegistry(self.db).register(
            AdapterManifestRegister(
                adapter_id=SOFTWARE_AGENT_ADAPTER_ID,
                version=SOFTWARE_AGENT_ADAPTER_VERSION,
                audience=SOFTWARE_AGENT_AUDIENCE,
                supported_action_types=[SOFTWARE_AGENT_ACTION_TYPE],
                reversible_only=True,
                supports_idempotency=True,
                supports_rollback=True,
                side_effect_free_preflight=True,
                external_dispatch_enabled=False,
                confirm=(
                    f"REGISTER ADAPTER {SOFTWARE_AGENT_ADAPTER_ID} "
                    f"{SOFTWARE_AGENT_ADAPTER_VERSION}"
                ),
            )
        )

    @staticmethod
    def capabilities() -> dict[str, Any]:
        return {
            "engine": "aura-software-engine-v1",
            "provider": SOFTWARE_AGENT_PROVIDER,
            "configured": bool(
                settings.software_agent_enabled
                and settings.software_agent_base_url
                and settings.software_agent_agent_profile_id
            ),
            "enabled": settings.software_agent_enabled,
            "adapter": {
                "adapter_id": SOFTWARE_AGENT_ADAPTER_ID,
                "version": SOFTWARE_AGENT_ADAPTER_VERSION,
                "audience": SOFTWARE_AGENT_AUDIENCE,
                "action_type": SOFTWARE_AGENT_ACTION_TYPE,
            },
            "allowed_repositories": sorted(_allowed_repositories()),
            "workspace_root": settings.software_agent_workspace_root,
            "worktree_required": True,
            "external_dispatch": False,
            "promotion_policy": "branch-test-canary-promote",
            "requires_authorized_preflight": True,
            "requires_sandbox_attestation": settings.software_agent_require_attestation,
            "goal_persisted": False,
            "final_response_persisted": False,
            "interrupt_supported": True,
        }

    def get_run(self, run_id: str) -> SoftwareAgentRun:
        run = (
            self.db.query(SoftwareAgentRun)
            .filter(SoftwareAgentRun.run_id == run_id)
            .one_or_none()
        )
        if not run:
            raise ValueError("software-agent run not found")
        return run

    def _require_preflight(
        self,
        preflight_id: str,
    ) -> tuple[AdapterPreflight, ExecutionAdapterManifest]:
        preflight = (
            self.db.query(AdapterPreflight)
            .filter(AdapterPreflight.preflight_id == preflight_id)
            .one_or_none()
        )
        if not preflight:
            raise ValueError("software-agent adapter preflight not found")
        if preflight.status != "contract_compatible":
            raise ValueError("software-agent adapter preflight is not contract compatible")
        if preflight.external_probe_performed or preflight.external_dispatch:
            raise ValueError("software-agent preflight must remain sandbox-local")

        manifest = (
            self.db.query(ExecutionAdapterManifest)
            .filter(ExecutionAdapterManifest.id == preflight.adapter_manifest_id)
            .one()
        )
        if (
            manifest.adapter_id != SOFTWARE_AGENT_ADAPTER_ID
            or manifest.version != SOFTWARE_AGENT_ADAPTER_VERSION
            or manifest.audience != SOFTWARE_AGENT_AUDIENCE
        ):
            raise ValueError("preflight does not belong to the AURA software engine")
        if preflight.action_type != SOFTWARE_AGENT_ACTION_TYPE:
            raise ValueError("preflight action is not a software patch mission")
        if manifest.external_dispatch_enabled:
            raise ValueError("software-agent manifest must not permit external dispatch")

        if settings.software_agent_require_attestation:
            attestation = SandboxAttestationService(self.db).effective_for_manifest(manifest)
            if attestation is None:
                raise ValueError("AURA software-engine sandbox runner is not effectively attested")
        return preflight, manifest

    @staticmethod
    def _workspace_path(repository: str) -> str:
        owner, name = repository.split("/", 1)
        return posixpath.join(
            settings.software_agent_workspace_root.rstrip("/"),
            owner,
            name,
        )

    @staticmethod
    def _mission_prompt(request: SoftwareAgentLaunchRequest, workspace_path: str) -> str:
        gates = request.quality_commands or [
            "Inspect the repository and run its native compile/lint/test checks.",
            "Run the narrowest relevant tests first, then the repository-wide checks when practical.",
        ]
        gate_text = "\n".join(f"- {item}" for item in gates)
        return (
            "You are the sandboxed software-engineering capability of AURA.\n"
            f"Repository: {request.repository}\n"
            f"Workspace: {workspace_path}\n\n"
            f"Mission:\n{request.goal.strip()}\n\n"
            "Non-negotiable execution contract:\n"
            "- Work only inside the dedicated OpenHands git worktree.\n"
            "- Never push, merge, deploy, publish, rotate secrets, or modify production infrastructure.\n"
            "- Never write directly to main/master or another protected base branch.\n"
            "- Keep the change minimal and reversible; preserve existing behavior outside the mission.\n"
            "- Do not print secrets or copy credentials into source files, logs, commits, or the final response.\n"
            "- If a quality gate fails, diagnose the failure, correct it, and rerun the relevant gate.\n"
            "- Do not claim success while a required gate is failing.\n"
            "- Finish with a concise list of changed files, tests run, remaining risks and rollback path.\n\n"
            "Required quality gates:\n"
            f"{gate_text}\n"
        )

    @staticmethod
    def _headers() -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if settings.software_agent_session_api_key:
            headers["X-Session-API-Key"] = settings.software_agent_session_api_key
        return headers

    @staticmethod
    def _url(path: str) -> str:
        return settings.software_agent_base_url.rstrip("/") + path

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if not settings.software_agent_base_url:
            raise ValueError("SOFTWARE_AGENT_BASE_URL is not configured")
        try:
            with httpx.Client(
                timeout=httpx.Timeout(settings.software_agent_timeout_seconds),
                follow_redirects=False,
            ) as client:
                response = client.request(
                    method,
                    self._url(path),
                    headers=self._headers(),
                    **kwargs,
                )
        except httpx.HTTPError as exc:
            raise ValueError("OpenHands Agent Server is unreachable") from exc
        if response.status_code >= 400:
            raise ValueError(
                f"OpenHands Agent Server rejected the request with HTTP {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError("OpenHands Agent Server returned non-JSON data") from exc
        if not isinstance(payload, dict):
            raise ValueError("OpenHands Agent Server returned an unexpected payload")
        return payload

    def launch(self, request: SoftwareAgentLaunchRequest) -> SoftwareAgentRun:
        if not settings.software_agent_enabled:
            raise ValueError("AURA software engine is disabled")
        if not settings.software_agent_agent_profile_id:
            raise ValueError("SOFTWARE_AGENT_AGENT_PROFILE_ID is not configured")
        try:
            uuid.UUID(settings.software_agent_agent_profile_id)
        except ValueError as exc:
            raise ValueError("SOFTWARE_AGENT_AGENT_PROFILE_ID must be a UUID") from exc

        repository_key = request.repository.lower()
        if repository_key not in _allowed_repositories():
            raise ValueError("repository is not allow-listed for AURA software-engine access")

        preflight, manifest = self._require_preflight(request.preflight_id)
        goal_hash = _sha256_text(request.goal.strip())
        existing = (
            self.db.query(SoftwareAgentRun)
            .filter(SoftwareAgentRun.idempotency_key == request.idempotency_key)
            .one_or_none()
        )
        if existing:
            if (
                existing.repository.lower() != repository_key
                or existing.goal_hash != goal_hash
                or existing.adapter_preflight_id != preflight.id
            ):
                raise ValueError("software-agent idempotency key is bound to another mission")
            return existing

        max_iterations = request.max_iterations or settings.software_agent_max_iterations
        if max_iterations > settings.software_agent_max_iterations:
            raise ValueError("requested max_iterations exceeds the configured software-agent ceiling")

        workspace_path = self._workspace_path(request.repository)
        run = SoftwareAgentRun(
            run_id=uuid.uuid4().hex,
            idempotency_key=request.idempotency_key,
            user_id=preflight.user_id,
            adapter_preflight_id=preflight.id,
            adapter_manifest_id=manifest.id,
            provider=SOFTWARE_AGENT_PROVIDER,
            repository=request.repository,
            workspace_path=workspace_path,
            goal_hash=goal_hash,
            quality_commands=request.quality_commands,
            max_iterations=max_iterations,
            worktree_required=True,
            external_dispatch=False,
            status="launching",
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)

        payload = {
            "agent_profile_id": settings.software_agent_agent_profile_id,
            "workspace": {
                "kind": "LocalWorkspace",
                "working_dir": workspace_path,
            },
            "worktree": True,
            "initial_message": {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": self._mission_prompt(request, workspace_path),
                    }
                ],
                "run": True,
            },
            "max_iterations": max_iterations,
            "stuck_detection": True,
            "tags": {
                "source": "aura",
                "mission": "software-engine",
                "repository": request.repository,
            },
        }

        try:
            response = self._request("POST", "/api/conversations", json=payload)
            conversation_id = str(response.get("id") or "").strip()
            if not conversation_id:
                raise ValueError("OpenHands Agent Server response has no conversation id")
            run.conversation_id = conversation_id
            run.execution_status = str(response.get("execution_status") or "running")
            run.status = "running"
            run.launched_at = datetime.utcnow()
            run.failure_reason = None
            user = self.db.query(User).filter(User.id == run.user_id).one()
            WorldModelService(self.db).append_event(
                user,
                EventCreate(
                    event_type="software_agent.sandbox_launched",
                    source="aura_software_engine",
                    subject_type="software_agent_run",
                    subject_id=run.run_id,
                    payload={
                        "repository": run.repository,
                        "provider": run.provider,
                        "conversation_id": run.conversation_id,
                        "goal_hash": run.goal_hash,
                        "worktree_required": True,
                        "external_dispatch": False,
                    },
                    correlation_id=f"software-agent:{run.run_id}",
                ),
                commit=False,
            )
            self.db.commit()
            self.db.refresh(run)
            return run
        except ValueError as exc:
            run.status = "failed"
            run.failure_reason = str(exc)[:500]
            run.completed_at = datetime.utcnow()
            self.db.commit()
            raise

    def refresh(self, run_id: str) -> tuple[SoftwareAgentRun, str | None]:
        run = self.get_run(run_id)
        if not run.conversation_id:
            return run, None

        response = self._request(
            "GET",
            f"/api/conversations/{run.conversation_id}",
        )
        execution_status = str(response.get("execution_status") or "unknown")
        run.execution_status = execution_status
        run.last_checked_at = datetime.utcnow()
        final_response: str | None = None

        if execution_status in _TERMINAL_EXECUTION_STATES:
            run.status = "completed" if execution_status == "finished" else "failed"
            run.completed_at = run.completed_at or datetime.utcnow()
            try:
                final_payload = self._request(
                    "GET",
                    f"/api/conversations/{run.conversation_id}/agent_final_response",
                )
                candidate = final_payload.get("response")
                if isinstance(candidate, str):
                    final_response = candidate
                    run.final_response_hash = _sha256_text(candidate)
            except ValueError:
                final_response = None
        elif execution_status in {"paused", "waiting_for_confirmation"}:
            run.status = execution_status
        else:
            run.status = "running"

        self.db.commit()
        self.db.refresh(run)
        return run, final_response

    def interrupt(self, run_id: str) -> SoftwareAgentRun:
        run = self.get_run(run_id)
        if not run.conversation_id:
            raise ValueError("software-agent run has no OpenHands conversation")
        if run.execution_status in _TERMINAL_EXECUTION_STATES:
            return run
        self._request(
            "POST",
            f"/api/conversations/{run.conversation_id}/interrupt",
            json={},
        )
        run.status = "interrupted"
        run.execution_status = "paused"
        run.last_checked_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(run)
        return run
