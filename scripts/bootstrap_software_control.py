from __future__ import annotations

import os
import time
from typing import Any

import httpx


CONTROL_BASE_URL = os.getenv("SOFTWARE_CONTROL_BASE_URL", "http://software-control:8001").rstrip("/")
CONTROL_API_KEY = os.getenv("HORIZON_API_KEY", "").strip()
WAIT_SECONDS = int(os.getenv("SOFTWARE_CONTROL_BOOTSTRAP_WAIT_SECONDS", "120"))


def _request(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    expected: set[int] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    headers = {"X-API-Key": CONTROL_API_KEY, "Content-Type": "application/json"}
    response = client.request(method, path, headers=headers, **kwargs)
    allowed = expected or {200}
    if response.status_code not in allowed:
        raise RuntimeError(
            f"software-control {method} {path} failed with HTTP "
            f"{response.status_code}: {response.text[:1000]}"
        )
    if not response.content:
        return {}
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def bootstrap() -> dict[str, Any]:
    if not CONTROL_API_KEY:
        raise RuntimeError("HORIZON_API_KEY is required")
    deadline = time.monotonic() + WAIT_SECONDS
    with httpx.Client(base_url=CONTROL_BASE_URL, timeout=30.0) as client:
        while time.monotonic() < deadline:
            try:
                ready = client.get("/ready", timeout=5.0)
                if ready.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(2)
        else:
            raise RuntimeError("software-control did not become ready")

        manifest = _request(
            client,
            "POST",
            "/v1/execution/software-agent/bootstrap",
            json={"confirm": "REGISTER AURA SOFTWARE ENGINE"},
        )
        capabilities = _request(
            client,
            "GET",
            "/v1/execution/software-agent/capabilities",
        )
        if capabilities.get("configured") is not True:
            raise RuntimeError(
                "software-control is running but the OpenHands profile id is not ready"
            )
        if capabilities.get("container_runtime_required") != "docker":
            raise RuntimeError("software-control lost the Docker-runtime invariant")
        return {"manifest": manifest, "capabilities": capabilities}


if __name__ == "__main__":
    result = bootstrap()
    print(
        "AURA Software Engine control plane ready:",
        result["manifest"].get("adapter_id"),
        result["manifest"].get("version"),
    )
