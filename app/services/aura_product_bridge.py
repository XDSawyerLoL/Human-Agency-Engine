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
AURA_TOKEN = os.getenv("AURA_CLOUD_TOKEN", "").strip()
BRIDGE_VERSION = "aura-universal-bridge-v1"

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
        return bool(AURA_TOKEN)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not AURA_TOKEN:
            return {}
        req = urllib.request.Request(
            AURA_URL + path,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {AURA_TOKEN}",
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
                    "/api/aura/everywhere/register",
                    {
                        **product,
                        "state": "online",
                        "permissions": ["observe", "propose-change", "test", "canary"],
                        "surfaces": ["analysis", "signals", "evidence"],
                        "metadata": {
                            "writable_by_aura": True,
                            "modification_policy": "branch-test-canary-promote",
                            "bridge_version": BRIDGE_VERSION,
                            "service": "human-agency-engine",
                            "personal_data_forwarded": False,
                        },
                    },
                )
            except Exception:
                continue

    def observe(self, product_id: str, state: str, detail: str = "", metadata: dict[str, Any] | None = None) -> None:
        if not self.enabled:
            return
        try:
            self._post(
                f"/api/aura/everywhere/{product_id}/observe",
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
