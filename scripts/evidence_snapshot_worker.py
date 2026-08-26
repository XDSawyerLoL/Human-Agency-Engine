from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time


RUNNING = True


def _stop(signum, frame):  # noqa: ARG001
    global RUNNING
    RUNNING = False


def _sleep_interruptibly(seconds: int) -> None:
    slept = 0
    while RUNNING and slept < seconds:
        chunk = min(1, seconds - slept)
        time.sleep(chunk)
        slept += chunk


def main() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    public_dir = Path(os.getenv("EVIDENCE_PUBLIC_DIR", "/public"))
    interval = max(60, int(os.getenv("EVIDENCE_SNAPSHOT_INTERVAL_SECONDS", "300")))
    forecast_limit = max(1, min(30, int(os.getenv("EVIDENCE_FORECAST_LIMIT", "20"))))
    public_dir.mkdir(parents=True, exist_ok=True)

    live = public_dir / "evidence-live.json"
    previous = public_dir / "evidence-previous.json"
    temporary = public_dir / "evidence-live.json.tmp"

    print(json.dumps({
        "service": "evidence-snapshot-worker",
        "status": "starting",
        "interval_seconds": interval,
        "forecast_limit": forecast_limit,
        "output": str(live),
    }), flush=True)

    while RUNNING:
        started = time.monotonic()
        try:
            if live.exists() and live.stat().st_size > 0:
                shutil.copy2(live, previous)
            elif not previous.exists():
                previous.write_text("{}\n", encoding="utf-8")

            command = [
                sys.executable,
                "scripts/evidence_public_snapshot.py",
                "--output",
                str(temporary),
                "--previous",
                str(previous),
                "--forecast-limit",
                str(forecast_limit),
            ]
            subprocess.run(command, check=True)
            if not temporary.exists() or temporary.stat().st_size == 0:
                raise RuntimeError("snapshot generator produced an empty file")
            temporary.replace(live)
            print(json.dumps({
                "service": "evidence-snapshot-worker",
                "status": "published",
                "bytes": live.stat().st_size,
                "duration_ms": int((time.monotonic() - started) * 1000),
            }), flush=True)
        except Exception as exc:
            if temporary.exists():
                temporary.unlink(missing_ok=True)
            print(json.dumps({
                "service": "evidence-snapshot-worker",
                "status": "error",
                "error": str(exc)[:2000],
            }), flush=True)

        elapsed = int(time.monotonic() - started)
        _sleep_interruptibly(max(1, interval - elapsed))

    print(json.dumps({"service": "evidence-snapshot-worker", "status": "stopped"}), flush=True)


if __name__ == "__main__":
    main()
