from __future__ import annotations

import json
import os
import signal
import socket
import time

from fastapi.encoders import jsonable_encoder

from app.config import settings
from app.db import SessionLocal
from app.services.horizon_corpus_worker import HorizonCorpusWorkerService


RUNNING = True


def _stop(signum, frame):  # noqa: ARG001
    global RUNNING
    RUNNING = False


def main() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    owner_id = os.getenv("HORIZON_CORPUS_WORKER_OWNER_ID") or f"corpus:{socket.gethostname()}:{os.getpid()}"
    interval = max(900, int(settings.horizon_corpus_worker_interval_seconds))
    lease_seconds = max(900, int(settings.horizon_corpus_worker_lease_seconds))

    if not settings.horizon_corpus_worker_enabled:
        print(json.dumps({"service": "horizon-corpus-worker", "status": "disabled"}), flush=True)
        return

    print(json.dumps({
        "service": "horizon-corpus-worker",
        "status": "starting",
        "owner_id": owner_id,
        "interval_seconds": interval,
        "engine": HorizonCorpusWorkerService.ENGINE_VERSION,
    }), flush=True)

    while RUNNING:
        db = SessionLocal()
        try:
            result = HorizonCorpusWorkerService(db).run_once(
                owner_id=owner_id,
                lease_seconds=lease_seconds,
                max_runs=settings.horizon_corpus_worker_max_runs_per_cycle,
                slices_per_run=settings.horizon_corpus_worker_slices_per_run,
            )
            print(json.dumps(jsonable_encoder(result), separators=(",", ":")), flush=True)
        except Exception as exc:
            db.rollback()
            print(json.dumps({
                "service": "horizon-corpus-worker",
                "status": "worker_error",
                "owner_id": owner_id,
                "error": str(exc)[:2000],
            }), flush=True)
        finally:
            db.close()

        slept = 0
        while RUNNING and slept < interval:
            chunk = min(1, interval - slept)
            time.sleep(chunk)
            slept += chunk

    print(json.dumps({"service": "horizon-corpus-worker", "status": "stopped", "owner_id": owner_id}), flush=True)


if __name__ == "__main__":
    main()
