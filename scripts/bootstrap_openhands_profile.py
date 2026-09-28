from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx


OPENHANDS_BASE_URL = os.getenv("OPENHANDS_BASE_URL", "http://openhands:8000").rstrip("/")
OPENHANDS_SESSION_API_KEY = os.getenv("OPENHANDS_SESSION_API_KEY", "").strip()
LLM_PROFILE_NAME = os.getenv("SOFTWARE_AGENT_LLM_PROFILE_NAME", "aura-local").strip()
AGENT_PROFILE_NAME = os.getenv("SOFTWARE_AGENT_PROFILE_NAME", "aura-software").strip()
LLM_MODEL = os.getenv("SOFTWARE_AGENT_LLM_MODEL", "").strip()
LLM_BASE_URL = os.getenv("SOFTWARE_AGENT_LLM_BASE_URL", "").strip()
LLM_API_KEY = os.getenv("SOFTWARE_AGENT_LLM_API_KEY", "local-llm").strip()
PROFILE_ID_FILE = Path(
    os.getenv(
        "SOFTWARE_AGENT_PROFILE_ID_FILE",
        "/software-control/agent-profile-id",
    )
)
WAIT_SECONDS = int(os.getenv("SOFTWARE_AGENT_BOOTSTRAP_WAIT_SECONDS", "180"))


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if OPENHANDS_SESSION_API_KEY:
        headers["X-Session-API-Key"] = OPENHANDS_SESSION_API_KEY
    return headers


def _request(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    expected: set[int] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    response = client.request(method, path, headers=_headers(), **kwargs)
    allowed = expected or {200}
    if response.status_code not in allowed:
        detail = response.text[:1000]
        raise RuntimeError(
            f"OpenHands {method} {path} failed with HTTP {response.status_code}: {detail}"
        )
    if not response.content:
        return {}
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"OpenHands {method} {path} returned a non-object JSON payload")
    return payload


def _wait_for_docker_runtime(client: httpx.Client) -> None:
    deadline = time.monotonic() + WAIT_SECONDS
    last_error = "not started"
    while time.monotonic() < deadline:
        try:
            info = _request(client, "GET", "/server_info")
            if info.get("conversation_runtime") != "docker":
                raise RuntimeError(
                    "OpenHands is reachable but conversation_runtime is not docker"
                )
            return
        except (httpx.HTTPError, RuntimeError) as exc:
            last_error = str(exc)
            time.sleep(2)
    raise RuntimeError(f"OpenHands Docker runtime did not become ready: {last_error}")


def _write_profile_id(profile_id: str) -> None:
    PROFILE_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=PROFILE_ID_FILE.parent,
        delete=False,
    ) as handle:
        handle.write(profile_id + "\n")
        temporary = Path(handle.name)
    temporary.chmod(0o600)
    temporary.replace(PROFILE_ID_FILE)


def bootstrap() -> str:
    if not OPENHANDS_SESSION_API_KEY:
        raise RuntimeError("OPENHANDS_SESSION_API_KEY is required")
    if not LLM_MODEL:
        raise RuntimeError("SOFTWARE_AGENT_LLM_MODEL is required")
    if not LLM_BASE_URL:
        raise RuntimeError("SOFTWARE_AGENT_LLM_BASE_URL is required")

    with httpx.Client(base_url=OPENHANDS_BASE_URL, timeout=120.0) as client:
        _wait_for_docker_runtime(client)

        llm = {
            "model": LLM_MODEL,
            "base_url": LLM_BASE_URL,
            "api_key": LLM_API_KEY or "local-llm",
        }
        validation = _request(
            client,
            "POST",
            f"/api/profiles/{LLM_PROFILE_NAME}/validate",
            json={"llm": llm},
        )
        if validation.get("valid") is not True:
            error = validation.get("error") or {}
            raise RuntimeError(
                "OpenHands LLM preflight failed: "
                + str(error.get("message") or error.get("type") or "unknown error")
            )

        _request(
            client,
            "POST",
            f"/api/profiles/{LLM_PROFILE_NAME}",
            expected={201},
            json={"llm": llm, "include_secrets": True},
        )
        _request(
            client,
            "POST",
            f"/api/agent-profiles/{AGENT_PROFILE_NAME}",
            expected={201},
            json={
                "agent_kind": "openhands",
                "llm_profile_ref": LLM_PROFILE_NAME,
                "mcp_server_refs": [],
                "secret_refs": [],
                "enable_sub_agents": False,
                "enable_switch_llm_tool": False,
                "tool_concurrency_limit": 1,
            },
        )

        materialized = _request(
            client,
            "POST",
            f"/api/agent-profiles/{AGENT_PROFILE_NAME}/materialize",
        )
        if materialized.get("valid") is not True:
            raise RuntimeError(
                "OpenHands agent profile failed materialization: "
                + "; ".join(str(item) for item in materialized.get("errors", []))
            )

        listing = _request(client, "GET", "/api/agent-profiles")
        profiles = listing.get("profiles")
        if not isinstance(profiles, list):
            raise RuntimeError("OpenHands agent profile listing is malformed")
        match = next(
            (
                item
                for item in profiles
                if isinstance(item, dict) and item.get("name") == AGENT_PROFILE_NAME
            ),
            None,
        )
        profile_id = str((match or {}).get("id") or "").strip()
        if not profile_id:
            raise RuntimeError("OpenHands agent profile has no stable id")

        _write_profile_id(profile_id)
        return profile_id


if __name__ == "__main__":
    profile_id = bootstrap()
    print(
        "AURA Software Engine OpenHands profile ready:",
        profile_id,
        "model=",
        LLM_MODEL,
        "base_url=",
        LLM_BASE_URL,
    )
