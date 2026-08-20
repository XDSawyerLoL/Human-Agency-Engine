from __future__ import annotations

import json
import os
import signal
import socket
import time

from fastapi.encoders import jsonable_encoder

from app.config import settings
from app.db import SessionLocal
from app.services.horizon_collector import HorizonCollectorService


RUNNING = True


def _stop(signum, frame):  # noqa: ARG001
    global RUNNING
    RUNNING = False


def main() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    owner_id = os.getenv("HORIZON_COLLECTOR_OWNER_ID") or f"{socket.gethostname()}:{os.getpid()}"
    tick = max(5, int(settings.horizon_collector_tick_seconds))

    if not settings.horizon_collector_enabled:
        print(json.dumps({"service": "horizon-collector", "status": "disabled"}), flush=True)
        return

    print(json.dumps({
        "service": "horizon-collector",
        "status": "starting",
        "owner_id": owner_id,
        "tick_seconds": tick,
        "engine": HorizonCollectorService.ENGINE_VERSION,
    }), flush=True)

    while RUNNING:
        started = time.monotonic()
        db = SessionLocal()
        try:
            result = HorizonCollectorService(db).run_due(owner_id=owner_id, trigger="worker")
            print(json.dumps(jsonable_encoder(result), separators=(",", ":")), flush=True)
        except Exception as exc:
            db.rollback()
            print(json.dumps({
                "service": "horizon-collector",
                "status": "worker_error",
                "owner_id": owner_id,
                "error": str(exc)[:2000],
            }), flush=True)
        finally:
            db.close()

        elapsed = time.monotonic() - started
        remaining = max(1.0, tick - elapsed)
        slept = 0.0
        while RUNNING and slept < remaining:
            chunk = min(1.0, remaining - slept)
            time.sleep(chunk)
            slept += chunk

    print(json.dumps({"service": "horizon-collector", "status": "stopped", "owner_id": owner_id}), flush=True)


if __name__ == "__main__":
    main()
