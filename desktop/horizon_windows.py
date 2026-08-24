from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import urllib.request


APP_NAME = "HORIZON"
HOST = "127.0.0.1"
PORT = 8765
DESKTOP_USER = "desktop-local"


def _bundle_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


def _data_root() -> Path:
    override = os.getenv("HORIZON_DESKTOP_DATA_DIR_OVERRIDE", "").strip()
    if override:
        path = Path(override)
        path.mkdir(parents=True, exist_ok=True)
        return path
    base = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _configure_environment(data_root: Path) -> None:
    db_path = data_root / "horizon.db"
    os.environ.setdefault("APP_ENV", "development")
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    os.environ["API_KEY"] = "change-me"
    os.environ["HORIZON_DESKTOP_MODE"] = "1"
    os.environ["HORIZON_DESKTOP_DATA_DIR"] = str(data_root)
    os.environ.setdefault("HORIZON_COLLECTOR_ENABLED", "true")
    os.environ.setdefault("HORIZON_COLLECTOR_TICK_SECONDS", "30")
    os.environ.setdefault("HORIZON_COLLECTOR_LEASE_SECONDS", "900")
    os.environ.setdefault("HORIZON_COLLECTOR_MAX_SOURCES_PER_CYCLE", "10")
    os.environ.setdefault("HORIZON_CORPUS_WORKER_ENABLED", "true")
    os.environ.setdefault("HORIZON_CORPUS_WORKER_INTERVAL_SECONDS", "21600")
    os.environ.setdefault("HORIZON_CORPUS_WORKER_LEASE_SECONDS", "7200")


def _run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    root = _bundle_root()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(config, "head")


def _ensure_desktop_user() -> None:
    from app.db import SessionLocal
    from app.models import User

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.external_id == DESKTOP_USER).one_or_none()
        if user is None:
            db.add(
                User(
                    external_id=DESKTOP_USER,
                    country="FR",
                    currency="EUR",
                    timezone="Europe/Paris",
                    preferences={
                        "runtime": "windows_desktop",
                        "created_by": "horizon_desktop_launcher",
                    },
                )
            )
            db.commit()
    finally:
        db.close()


def _run_collector(stop_event: threading.Event) -> None:
    from app.config import settings
    from app.db import SessionLocal
    from app.services.horizon_collector import HorizonCollectorService

    owner_id = f"windows-desktop:{os.getpid()}"
    tick = max(5, int(settings.horizon_collector_tick_seconds))
    while not stop_event.is_set():
        started = time.monotonic()
        db = SessionLocal()
        try:
            HorizonCollectorService(db).run_due(owner_id=owner_id, trigger="windows-desktop")
        except Exception:
            db.rollback()
        finally:
            db.close()

        elapsed = time.monotonic() - started
        stop_event.wait(max(1.0, tick - elapsed))


def _run_corpus_worker(stop_event: threading.Event) -> None:
    from app.config import settings
    from app.db import SessionLocal
    from app.services.horizon_corpus_worker import HorizonCorpusWorkerService

    owner_id = f"windows-corpus:{os.getpid()}"
    interval = max(900, int(settings.horizon_corpus_worker_interval_seconds))
    while not stop_event.is_set():
        db = SessionLocal()
        try:
            HorizonCorpusWorkerService(db).run_once(
                owner_id=owner_id,
                lease_seconds=max(900, int(settings.horizon_corpus_worker_lease_seconds)),
                max_runs=settings.horizon_corpus_worker_max_runs_per_cycle,
                slices_per_run=settings.horizon_corpus_worker_slices_per_run,
            )
        except Exception:
            db.rollback()
        finally:
            db.close()
        stop_event.wait(interval)


def _run_server(stop_event: threading.Event):
    import uvicorn
    from app.horizon_api import app

    config = uvicorn.Config(
        app,
        host=HOST,
        port=PORT,
        log_level="warning",
        access_log=False,
        loop="asyncio",
    )
    server = uvicorn.Server(config)

    def stop_server():
        stop_event.wait()
        server.should_exit = True

    threading.Thread(target=stop_server, daemon=True).start()
    server.run()


def _wait_until_ready(timeout_seconds: float = 60.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    url = f"http://{HOST}:{PORT}/ready"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("HORIZON local API did not become ready")


def _find_edge() -> Path | None:
    candidates = [
        Path(os.getenv("PROGRAMFILES(X86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.getenv("PROGRAMFILES", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.getenv("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    ]
    command = shutil.which("msedge")
    if command:
        candidates.insert(0, Path(command))
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    return None


def _find_chrome() -> Path | None:
    candidates = [
        Path(os.getenv("PROGRAMFILES", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.getenv("PROGRAMFILES(X86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.getenv("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    command = shutil.which("chrome")
    if command:
        candidates.insert(0, Path(command))
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    return None


def _open_app_window(data_root: Path) -> subprocess.Popen | None:
    url = f"http://{HOST}:{PORT}/ui/?desktop=1"
    browser = _find_edge() or _find_chrome()
    if browser is not None:
        profile = data_root / "BrowserProfile"
        profile.mkdir(parents=True, exist_ok=True)
        args = [
            str(browser),
            f"--app={url}",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--disable-sync",
            "--disable-extensions",
        ]
        return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    import webbrowser
    webbrowser.open(url)
    return None


def _monitor_window(stop_event: threading.Event, process: subprocess.Popen | None) -> None:
    from app.desktop_runtime import heartbeat_status

    started = time.monotonic()
    while not stop_event.is_set():
        status = heartbeat_status()
        age = status["age_seconds"]

        if status["seen"] and age is not None and age > 35:
            stop_event.set()
            return

        if not status["seen"] and time.monotonic() - started > 120:
            # The UI never contacted the local runtime.
            stop_event.set()
            return

        # Browser app processes can hand off to a child process, so process exit is
        # intentionally not the shutdown signal. The UI heartbeat is authoritative.
        stop_event.wait(2)


def _self_test(data_root: Path) -> int:
    _configure_environment(data_root)
    _run_migrations()
    _ensure_desktop_user()

    from fastapi.testclient import TestClient
    from app.horizon_api import app

    api = TestClient(app)
    health = api.get("/health")
    ready = api.get("/ready")
    briefing = api.get("/v1/horizon/world/briefing", params={"external_id": DESKTOP_USER})
    if health.status_code != 200:
        raise RuntimeError(f"health failed: {health.status_code}")
    if ready.status_code != 200:
        raise RuntimeError(f"ready failed: {ready.status_code}")
    if briefing.status_code != 200:
        raise RuntimeError(f"briefing failed: {briefing.status_code}")
    if not health.json().get("windows_desktop_runtime_supported"):
        raise RuntimeError("desktop capability flag missing")
    return 0


def main() -> int:
    data_root = _data_root()
    _configure_environment(data_root)

    if "--self-test" in sys.argv:
        try:
            return _self_test(data_root)
        except Exception as exc:
            print(f"HORIZON self-test failed: {exc}", file=sys.stderr)
            return 90

    try:
        _run_migrations()
        _ensure_desktop_user()
    except Exception as exc:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            f"HORIZON n'a pas pu initialiser sa base locale.\n\n{exc}",
            APP_NAME,
            0x10,
        )
        return 1

    stop_event = threading.Event()

    server_thread = threading.Thread(
        target=_run_server,
        args=(stop_event,),
        name="horizon-local-api",
        daemon=True,
    )
    server_thread.start()

    try:
        _wait_until_ready()
    except Exception as exc:
        stop_event.set()
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            f"HORIZON n'a pas pu démarrer son moteur local.\n\n{exc}",
            APP_NAME,
            0x10,
        )
        return 2

    threading.Thread(
        target=_run_collector,
        args=(stop_event,),
        name="horizon-collector",
        daemon=True,
    ).start()

    threading.Thread(
        target=_run_corpus_worker,
        args=(stop_event,),
        name="horizon-corpus-worker",
        daemon=True,
    ).start()

    process = _open_app_window(data_root)
    _monitor_window(stop_event, process)
    stop_event.set()
    server_thread.join(timeout=8)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
