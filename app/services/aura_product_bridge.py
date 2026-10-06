from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from typing import Any

AURA_URL = os.getenv(
    "AURA_CLOUD_URL",
    "https://antiquewhite-dolphin-780448.hostingersite.com",
).rstrip("/")
LEGACY_ALLOWED = os.getenv("AURA_ALLOW_LEGACY_PRODUCT_ADMIN_TOKEN", "").strip().lower() in {"1", "true", "yes", "oui", "on"}
LEGACY_TOKEN = os.getenv("AURA_CLOUD_TOKEN", "").strip() if LEGACY_ALLOWED else ""
PRODUCT_TOKENS = {
    "providence": (
        os.getenv("AURA_PROVIDENCE_TOKEN", "").strip()
        or os.getenv("AURA_PRODUCT_TOKEN_PROVIDENCE", "").strip()
    ),
    "horizon": (
        os.getenv("AURA_HORIZON_TOKEN", "").strip()
        or os.getenv("AURA_PRODUCT_TOKEN_HORIZON", "").strip()
    ),
    "aura-software-engine": (
        os.getenv("AURA_SOFTWARE_ENGINE_TOKEN", "").strip()
        or os.getenv("AURA_PRODUCT_TOKEN_AURA_SOFTWARE_ENGINE", "").strip()
    ),
}
BRIDGE_VERSION = "aura-universal-bridge-v2-scoped"


def token_for(product_id: str) -> str:
    return PRODUCT_TOKENS.get(product_id, "") or LEGACY_TOKEN

PRODUCTS = (
    {
        "id": "providence",
        "name": "Providence",
        "objective": "Analyse profonde, signaux, scénarios, risques et aide à la décision.",
        "repository": "XDSawyerLoL/Human-Agency-Engine",
        "criticality": 0.88,
        "capabilities": ["analysis", "signals", "risk", "scenarios", "evidence"],
    },
    {
        "id": "horizon",
        "name": "HORIZON",
        "objective": "Perception du monde, signaux externes et chaînes d’impact pour AURA.",
        "repository": "XDSawyerLoL/Human-Agency-Engine",
        "criticality": 0.86,
        "capabilities": ["world-signals", "weather", "impact-chain", "forecast-context"],
    },
)

if os.getenv("SOFTWARE_AGENT_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}:
    PRODUCTS += (
        {
            "id": "aura-software-engine",
            "name": "AURA Software Engine",
            "objective": "Ingénierie logicielle sandboxée, testable, interruptible et sans promotion directe.",
            "repository": "XDSawyerLoL/Human-Agency-Engine",
            "criticality": 0.90,
            "capabilities": [
                "software-engineering",
                "git-worktree",
                "test-loop",
                "rollback",
                "openhands-agent-server",
            ],
        },
    )


class AuraProductBridge:
    """Operational-only bridge from Human Agency Engine to AURA.

    User records, forecasts and personal content are not forwarded by this
    heartbeat. Existing HORIZON/AURA routes retain their own epistemic contract.
    """

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def enabled(self) -> bool:
        return any(token_for(product["id"]) for product in PRODUCTS)

    def _post(self, product_id: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        token = token_for(product_id)
        if not token:
            return {}
        req = urllib.request.Request(
            AURA_URL + path,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "Human-Agency-Engine/AURA-Bridge-1",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            return json.loads(response.read().decode("utf-8") or "{}")

    def register(self) -> None:
        if not self.enabled:
            return
        for product in PRODUCTS:
            try:
                self._post(
                    product["id"],
                    "/api/aura/products/register",
                    {
                        **product,
                        "state": "online",
                        "writable_by_aura": True,
                        "modification_policy": "branch-test-canary-promote",
                        "bridge_version": BRIDGE_VERSION,
                        "runtime": {
                            "service": "human-agency-engine",
                            "personal_data_forwarded": False,
                        },
                    },
                )
            except Exception:
                continue

    def observe(self, product_id: str, state: str, detail: str = "", metadata: dict[str, Any] | None = None) -> None:
        if not token_for(product_id):
            return
        try:
            self._post(
                product_id,
                f"/api/aura/products/{product_id}/observe",
                {
                    "state": state,
                    "detail": detail,
                    "metadata": {
                        **(metadata or {}),
                        "bridge_version": BRIDGE_VERSION,
                        "personal_data_forwarded": False,
                    },
                },
            )
        except Exception:
            pass

    def _heartbeat(self) -> None:
        self.register()
        while not self._stop.wait(120):
            for product in PRODUCTS:
                self.observe(product["id"], "online", "Human Agency Engine actif.")

    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._heartbeat,
            name="aura-product-bridge",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._thread is None:
            return
        self._stop.set()
        self._thread.join(timeout=1)
        self._thread = None


aura_product_bridge = AuraProductBridge()
