from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class ServiceTarget:
    id: str
    label: str
    kind: str
    public_url: str
    probe_url: str | None = None
    state: str = "active"


QUANTIC_SERVICE_TARGETS: tuple[ServiceTarget, ...] = (
    ServiceTarget(
        id="vision",
        label="Quantic Vision",
        kind="vision",
        public_url="/vision/",
        probe_url=None,
    ),
    ServiceTarget(
        id="mail",
        label="Quantic Mail",
        kind="application",
        public_url="https://quanticmail.onrender.com",
        probe_url="https://quanticmail.onrender.com",
    ),
    ServiceTarget(
        id="relay-render",
        label="Quantic Relay · Render",
        kind="relay",
        public_url="https://quanticmail-network-relay.onrender.com",
        probe_url="https://quanticmail-network-relay.onrender.com",
    ),
    ServiceTarget(
        id="relay-railway",
        label="Quantic Relay · Railway",
        kind="relay",
        public_url="https://quantic-network-relay-backup-production.up.railway.app",
        probe_url="https://quantic-network-relay-backup-production.up.railway.app",
    ),
    ServiceTarget(
        id="relay-hostinger",
        label="Quantic Relay · Hostinger",
        kind="relay",
        public_url="/network/",
        probe_url=None,
        state="pending",
    ),
)


def probe_service(target: ServiceTarget, *, timeout: float = 2.5) -> dict[str, object]:
    """Probe one immutable Quantic target without exposing response content."""
    if target.id == "vision" and target.probe_url is None:
        # This function runs inside the Vision API process. If it can build the
        # status response, the local Vision service is alive by definition.
        return {"reachable": True, "http_status": 200}
    if target.probe_url is None:
        return {"reachable": None, "http_status": None}

    request = Request(
        target.probe_url,
        method="GET",
        headers={"User-Agent": "Quantic-Portal-Health/1.0", "Accept": "*/*"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - immutable HTTPS allowlist
            status = int(getattr(response, "status", 200))
            return {"reachable": status < 500, "http_status": status}
    except HTTPError as error:
        status = int(error.code)
        # 4xx still proves that the remote HTTP service is reachable. The
        # portal is checking transport availability, not endpoint semantics.
        return {"reachable": status < 500, "http_status": status}
    except (URLError, TimeoutError, OSError):
        return {"reachable": False, "http_status": None}


def _service_payload(target: ServiceTarget, result: dict[str, object] | None) -> dict[str, object]:
    reachable = None if result is None else result.get("reachable")
    http_status = None if result is None else result.get("http_status")
    return {
        "id": target.id,
        "label": target.label,
        "kind": target.kind,
        "url": target.public_url,
        "state": target.state,
        "reachable": reachable,
        "http_status": http_status,
    }


def _safe_probe(
    target: ServiceTarget,
    probe: Callable[[ServiceTarget], dict[str, object]],
) -> dict[str, object]:
    try:
        return probe(target)
    except Exception:
        # The public endpoint never leaks an exception body, hostname
        # resolution detail, credential, stack trace or provider message.
        return {"reachable": False, "http_status": None}


def build_portal_status(
    probe: Callable[[ServiceTarget], dict[str, object]] = probe_service,
) -> dict[str, object]:
    active_targets = [target for target in QUANTIC_SERVICE_TARGETS if target.state != "pending"]
    results: dict[str, dict[str, object]] = {}

    if active_targets:
        with ThreadPoolExecutor(max_workers=len(active_targets), thread_name_prefix="quantic-status") as pool:
            futures = {
                target.id: pool.submit(_safe_probe, target, probe)
                for target in active_targets
            }
            results = {service_id: future.result() for service_id, future in futures.items()}

    services = [
        _service_payload(target, None if target.state == "pending" else results[target.id])
        for target in QUANTIC_SERVICE_TARGETS
    ]
    return {"status": "ok", "services": services}
