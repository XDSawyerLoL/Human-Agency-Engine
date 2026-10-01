from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..config import settings


VALID_STATES = ("ACTIVE", "DEGRADED", "DISABLED", "MISSING")


def _capability(
    capability_id: str,
    label: str,
    category: str,
    state: str,
    *,
    summary: str,
    evidence: list[str],
    limitations: list[str] | None = None,
    public_action: str | None = None,
) -> dict[str, Any]:
    if state not in VALID_STATES:
        raise ValueError(f"invalid AURA capability state: {state}")
    return {
        "id": capability_id,
        "label": label,
        "category": category,
        "state": state,
        "summary": summary,
        "evidence": evidence,
        "limitations": limitations or [],
        "public_action": public_action,
    }


def build_aura_capability_registry() -> dict[str, Any]:
    """Return a conservative, public-safe snapshot of AURA's real capabilities.

    The registry intentionally reports disabled and missing pieces instead of
    inferring readiness from source-code presence alone. It exposes no secrets,
    user data, provider credentials, or private mission payloads.
    """

    personal_agent_state = "ACTIVE" if settings.personal_agent_enabled else "DISABLED"
    software_engine_state = "ACTIVE" if settings.software_agent_enabled else "DISABLED"
    bounded_autonomy_state = "DEGRADED" if settings.personal_agent_enabled else "DISABLED"

    capabilities = [
        _capability(
            "world_intelligence",
            "HORIZON world intelligence",
            "perception",
            "ACTIVE",
            summary="Multi-domain observation, evidence convergence, event graph and forecast ledger are implemented on the production HORIZON surface.",
            evidence=[
                "app.horizon_api mounts dedicated HORIZON routers",
                "GET /v1/horizon/world/coverage reports domain maturity",
                "GET /v1/horizon/world/briefing exposes the unified world view",
            ],
            public_action="/ui/",
        ),
        _capability(
            "persistent_context",
            "Persistent context and intentions",
            "memory",
            "ACTIVE",
            summary="AURA can persist user state facts and intents in the Human Agency Engine data model.",
            evidence=[
                "PUT /v1/horizon/context/users/{external_id}",
                "POST /v1/horizon/context/users/{external_id}/state/facts",
                "POST /v1/horizon/context/users/{external_id}/intents",
            ],
            limitations=[
                "Persistence alone does not prove conversational continuity.",
                "The dialogue layer must still consume this state consistently.",
            ],
        ),
        _capability(
            "horizon_cognitive_bridge",
            "HORIZON -> AURA cognitive bridge",
            "integration",
            "ACTIVE",
            summary="A dedicated bridge exposes HORIZON evidence to AURA without mounting the historical action surface.",
            evidence=[
                "GET /v1/horizon/aura/feed",
                "GET /v1/horizon/aura/capabilities",
            ],
            limitations=["The bridge supplies evidence; it is not a complete autonomous cognition loop."],
        ),
        _capability(
            "persistent_missions",
            "Persistent personal-agent missions",
            "agency",
            personal_agent_state,
            summary="AURA can store, resume, pause and execute bounded missions when the personal-agent runtime is enabled.",
            evidence=[
                "app.services.personal_agent.PersonalAgentService",
                "GET /v1/personal-agent/runtime on the legacy/agent control surface",
            ],
            limitations=[
                "The production HORIZON app intentionally does not mount the personal-agent action routes.",
                "Current mission task types are bounded rather than open-ended.",
            ],
        ),
        _capability(
            "background_scheduler",
            "Autonomous background scheduler",
            "agency",
            personal_agent_state,
            summary="A bounded scheduler can run due missions periodically without a new user prompt.",
            evidence=["PersonalAgentRuntime.tick()", "PERSONAL_AGENT_TICK_SECONDS configuration"],
            limitations=["Disabled by configuration when PERSONAL_AGENT_ENABLED is false."],
        ),
        _capability(
            "software_engine",
            "AURA Software Engine",
            "action",
            software_engine_state,
            summary="AURA can inspect, modify and test code in an isolated OpenHands/Docker worktree when explicitly enabled and authorized.",
            evidence=[
                "app.services.software_agent",
                "docs/AURA_SOFTWARE_ENGINE.md",
            ],
            limitations=[
                "Sandbox only.",
                "No direct push, merge, production deployment or secret rotation.",
            ],
        ),
        _capability(
            "google_readonly",
            "Google read-only connector",
            "connector",
            "DEGRADED",
            summary="A read-only Google connector exists, but actual availability depends on a per-user connected account.",
            evidence=["app.connectors.google.GoogleReadOnlyConnector"],
            limitations=["Registry cannot claim a user account is connected from a public generic endpoint."],
        ),
        _capability(
            "conversation_continuity",
            "Conversation-state continuity",
            "cognition",
            "DEGRADED",
            summary="Memory, intents and missions exist, but they are not yet proven to be consistently unified into every conversational answer.",
            evidence=[
                "Persistent context exists",
                "Persistent missions exist",
                "GET /v1/aura/users/{external_id}/activity exposes a protected persisted current-work snapshot",
            ],
            limitations=[
                "The dialogue surface must still be wired to consume the activity snapshot on current-work questions.",
                "This capability requires behavioral verification, not only code inspection.",
            ],
        ),
        _capability(
            "general_autonomy_loop",
            "General autonomy loop",
            "agency",
            bounded_autonomy_state,
            summary="AURA has a bounded autonomous mission loop but not yet a demonstrated general self-directed loop across arbitrary tools and goals.",
            evidence=[
                "PersonalAgentService dispatches connector_sync, agency_cycle and software_patch",
            ],
            limitations=[
                "No demonstrated general goal generation and reprioritization loop.",
                "No complete operator bus across browser, desktop and Quantic products.",
            ],
        ),
        _capability(
            "browser_operator",
            "Browser operator",
            "action",
            "MISSING",
            summary="A real browser-control operator is not configured in the current personal-agent runtime.",
            evidence=["PersonalAgentService.capabilities reports browser_use unavailable"],
            limitations=["Required for autonomous web navigation and form interaction."],
        ),
        _capability(
            "computer_operator",
            "Graphical computer operator",
            "action",
            "MISSING",
            summary="A graphical computer-control operator is not configured.",
            evidence=["PersonalAgentService.capabilities reports computer_use unavailable"],
            limitations=["Required for arbitrary desktop GUI workflows."],
        ),
        _capability(
            "quantic_operator_bus",
            "Quantic product operator bus",
            "integration",
            "MISSING",
            summary="Glide, Mail, ZOON and Studio do not yet share one attested operator bus controlled by AURA.",
            evidence=["docs/AURA_PERSONAL_AGENT_RUNTIME.md lists this as a next layer"],
            limitations=["Product-specific integrations may exist elsewhere, but no unified action bus is demonstrated here."],
        ),
        _capability(
            "aura_eval",
            "AURA-Eval blind benchmark",
            "verification",
            "ACTIVE",
            summary="A 50-slot holdout benchmark contract is versioned in the repository while concrete prompts and answers remain external to the agent-visible repository.",
            evidence=[
                "aura_eval/manifest.json",
                "aura_eval/README.md",
            ],
            limitations=[
                "A capability score is not produced until a hidden holdout corpus and target adapter are executed.",
                "External GPT comparisons require equivalent tool access and independently recorded runs.",
            ],
        ),
        _capability(
            "energy_telemetry",
            "End-to-end energy telemetry",
            "efficiency",
            "MISSING",
            summary="AURA does not yet provide trustworthy end-to-end joule accounting across local compute and remote model providers.",
            evidence=["No repository evidence of unified local + remote joule metering"],
            limitations=[
                "Token counts, latency and local CPU/GPU energy can be measured as separate proxies.",
                "A 50% energy-reduction claim must not be made until mission-level telemetry exists.",
            ],
        ),
    ]

    counts = {state: 0 for state in VALID_STATES}
    for item in capabilities:
        counts[item["state"]] += 1

    return {
        "registry": "aura-capability-registry-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "truth_policy": "source presence is not treated as runtime readiness",
        "states": list(VALID_STATES),
        "summary": {
            "total": len(capabilities),
            **{state.lower(): count for state, count in counts.items()},
        },
        "capabilities": capabilities,
    }
