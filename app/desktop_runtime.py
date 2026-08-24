from __future__ import annotations

import threading
import time


_lock = threading.Lock()
_last_heartbeat = 0.0
_heartbeat_seen = False


def touch_heartbeat() -> None:
    global _last_heartbeat, _heartbeat_seen
    with _lock:
        _last_heartbeat = time.monotonic()
        _heartbeat_seen = True


def heartbeat_status() -> dict:
    with _lock:
        now = time.monotonic()
        age = None if not _heartbeat_seen else max(0.0, now - _last_heartbeat)
        return {
            "seen": _heartbeat_seen,
            "age_seconds": age,
        }
