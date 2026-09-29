from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from ..adapter_models import AdapterPreflight
from ..config import settings
from ..connectors.google import GoogleReadOnlyConnector
from ..db import SessionLocal
from ..models import ConnectorAccount, User
from ..personal_agent_models import PersonalAgentMission, PersonalAgentMissionRun
from ..personal_agent_schemas import PersonalAgentMissionCreate
from ..software_agent_schemas import SoftwareAgentLaunchRequest
from .acquisition import InformationAcquisitionService
from .engine import OpportunityEngine
from .crypto import TokenCipher
from .software_agent import SoftwareAgentSandboxService
from .synthesis import SynthesisService


class PersonalAgentService:
    """Persistent mission scheduler and bounded execution layer for AURA.

    The runtime may perform read/analysis work automatically and may launch the
    existing reversible software sandbox only when the mission references an
    already-authorized software-agent preflight. It does not deploy, publish,
    send messages, or control a graphical desktop.
    """

    def __init__(self, db: Session):
        self.db = db

    def capabilities(self, user: User) -> dict[str, Any]:
        google_connected = (
            self.db.query(ConnectorAccount)
            .filter(
                ConnectorAccount.user_id == user.id,
                ConnectorAccount.provider == "google",
                ConnectorAccount.enabled == True,  # noqa: E712
            )
            .first()
            is not None
        )
        return {
            "runtime": "aura-personal-agent-v1",
            "scheduler": {
                "available": True,
                "background_enabled": settings.personal_agent_enabled,
                "tick_seconds": settings.personal_agent_tick_seconds,
            },
            "capabilities": {
                "agency_cycle": {"available": True, "external_dispatch": False},
                "connector_sync": {
                    "available": google_connected,
                    "provider": "google-readonly",
                    "external_dispatch": False,
                },
                "software_patch": {
                    "available": settings.software_agent_enabled,
                    "provider": "aura-software-engine",
                    "sandbox_only": True,
                    "external_dispatch": False,
                },
                "browser_use": {
                    "available": False,
                    "reason": "browser operator not configured",
                },
                "computer_use": {
                    "available": False,
                    "reason": "graphical cloud computer not configured",
                },
                "slack": {"available": False, "reason": "connector not configured"},
                "sms": {"available": False, "reason": "connector not configured"},
            },
        }

    def create(self, user: User, payload: PersonalAgentMissionCreate) -> PersonalAgentMission:
        now = datetime.utcnow()
        next_run_at = None
        if payload.trigger_type == "interval":
            next_run_at = now if payload.start_immediately else now + timedelta(
                seconds=payload.interval_seconds or 60
            )
        goal = payload.goal.strip()
        task_payload = dict(payload.task_payload)
        if payload.task_type == "software_patch":
            embedded_goal = str(task_payload.pop("goal", "") or "").strip()
            if embedded_goal and embedded_goal != goal:
                raise ValueError("software_patch task_payload goal must match the mission goal")
        cipher = TokenCipher()
        mission = PersonalAgentMission(
            mission_id=uuid.uuid4().hex,
            user_id=user.id,
            title=payload.title.strip(),
            goal_hash="sha256:" + hashlib.sha256(goal.encode("utf-8")).hexdigest(),
            encrypted_goal=cipher.encrypt(goal),
            task_type=payload.task_type,
            autonomy_level=payload.autonomy_level,
            required_capabilities=payload.required_capabilities,
            encrypted_task_payload=cipher.encrypt(
                json.dumps(task_payload, ensure_ascii=False, sort_keys=True)
            ),
            trigger_type=payload.trigger_type,
            interval_seconds=payload.interval_seconds,
            status="active",
            run_count=0,
            max_runs=payload.max_runs,
            next_run_at=next_run_at,
            created_at=now,
            updated_at=now,
        )
        self.db.add(mission)
        self.db.commit()
        self.db.refresh(mission)
        return mission

    def get(self, mission_id: str) -> PersonalAgentMission:
        mission = (
            self.db.query(PersonalAgentMission)
            .filter(PersonalAgentMission.mission_id == mission_id)
            .one_or_none()
        )
        if not mission:
            raise ValueError("personal-agent mission not found")
        return mission

    def list_for_user(self, user: User) -> list[PersonalAgentMission]:
        return (
            self.db.query(PersonalAgentMission)
            .filter(PersonalAgentMission.user_id == user.id)
            .order_by(PersonalAgentMission.created_at.desc())
            .all()
        )

    def pause(self, user: User, mission_id: str, reason: str = "") -> PersonalAgentMission:
        mission = self.get(mission_id)
        if mission.user_id != user.id:
            raise ValueError("personal-agent mission does not belong to user")
        if mission.status == "running":
            raise ValueError("cannot pause a running personal-agent mission")
        if mission.status == "completed":
            raise ValueError("completed personal-agent mission cannot be paused")
        mission.status = "paused"
        mission.last_error = reason.strip()
        mission.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(mission)
        return mission

    def resume(self, user: User, mission_id: str) -> PersonalAgentMission:
        mission = self.get(mission_id)
        if mission.user_id != user.id:
            raise ValueError("personal-agent mission does not belong to user")
        if mission.status == "completed":
            raise ValueError("completed personal-agent mission cannot be resumed")
        mission.status = "active"
        mission.last_error = ""
        mission.updated_at = datetime.utcnow()
        if mission.trigger_type == "interval":
            mission.next_run_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(mission)
        return mission

    def cancel(self, user: User, mission_id: str, reason: str = "") -> PersonalAgentMission:
        mission = self.get(mission_id)
        if mission.user_id != user.id:
            raise ValueError("personal-agent mission does not belong to user")
        if mission.status == "running":
            raise ValueError("cannot cancel a running mission through the scheduler")
        mission.status = "completed"
        mission.next_run_at = None
        mission.last_error = reason.strip()
        mission.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(mission)
        return mission

    def list_runs(self, mission: PersonalAgentMission) -> list[PersonalAgentMissionRun]:
        return (
            self.db.query(PersonalAgentMissionRun)
            .filter(PersonalAgentMissionRun.mission_id == mission.id)
            .order_by(PersonalAgentMissionRun.started_at.desc())
            .all()
        )

    @staticmethod
    def _decrypt_goal(mission: PersonalAgentMission) -> str:
        return TokenCipher().decrypt(mission.encrypted_goal)

    @staticmethod
    def _decrypt_task_payload(mission: PersonalAgentMission) -> dict[str, Any]:
        raw = TokenCipher().decrypt(mission.encrypted_task_payload)
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("personal-agent task payload is not an object")
        return payload

    def _capability_available(self, user: User, capability: str) -> bool:
        state = self.capabilities(user)["capabilities"].get(capability)
        return bool(state and state.get("available"))

    def _validate_required_capabilities(self, user: User, mission: PersonalAgentMission) -> None:
        unavailable = [
            capability
            for capability in mission.required_capabilities
            if not self._capability_available(user, capability)
        ]
        if unavailable:
            raise ValueError(
                "required personal-agent capabilities unavailable: " + ", ".join(sorted(unavailable))
            )

    def _sync_connectors(self, user: User) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        accounts = (
            self.db.query(ConnectorAccount)
            .filter(
                ConnectorAccount.user_id == user.id,
                ConnectorAccount.enabled == True,  # noqa: E712
            )
            .all()
        )
        for account in accounts:
            if account.provider == "google":
                try:
                    results.append(GoogleReadOnlyConnector(self.db).sync(account.id))
                except Exception as exc:
                    results.append(
                        {
                            "provider": account.provider,
                            "account_id": account.id,
                            "error": str(exc)[:500],
                        }
                    )
            else:
                results.append(
                    {
                        "provider": account.provider,
                        "account_id": account.id,
                        "skipped": True,
                        "reason": "provider is not registered in personal-agent v1",
                    }
                )
        return results

    def _run_agency_cycle(self, user: User) -> dict[str, Any]:
        connectors = self._sync_connectors(user)
        opportunities = OpportunityEngine(self.db).run_for_user(user)
        synthesis = SynthesisService(self.db).run(user)
        acquisition = InformationAcquisitionService(self.db).materialize(user)
        return {
            "connectors": connectors,
            "created_opportunities": len(opportunities),
            "synthesis": synthesis,
            "information_acquisition": acquisition,
            "external_dispatch": False,
        }

    def _run_software_patch(
        self,
        user: User,
        mission: PersonalAgentMission,
    ) -> tuple[dict[str, Any], str]:
        if mission.autonomy_level != "execute_reversible":
            raise ValueError("software_patch mission is not authorized for reversible execution")
        try:
            payload = self._decrypt_task_payload(mission)
            request = SoftwareAgentLaunchRequest(
                **payload,
                goal=self._decrypt_goal(mission),
            )
        except Exception as exc:
            raise ValueError("software_patch task_payload is invalid") from exc

        preflight = (
            self.db.query(AdapterPreflight)
            .filter(AdapterPreflight.preflight_id == request.preflight_id)
            .one_or_none()
        )
        if preflight is None:
            raise ValueError("software_patch preflight does not exist")
        if preflight.user_id != user.id:
            raise ValueError("software_patch preflight belongs to another user")

        run = SoftwareAgentSandboxService(self.db).launch(request)
        return (
            {
                "software_agent_run_id": run.run_id,
                "status": run.status,
                "execution_status": run.execution_status,
                "repository": run.repository,
                "sandbox_only": True,
                "external_dispatch": False,
            },
            run.run_id,
        )

    def _dispatch(
        self,
        user: User,
        mission: PersonalAgentMission,
    ) -> tuple[dict[str, Any], str | None]:
        self._validate_required_capabilities(user, mission)
        if mission.task_type == "connector_sync":
            return (
                {
                    "connectors": self._sync_connectors(user),
                    "external_dispatch": False,
                },
                None,
            )
        if mission.task_type == "agency_cycle":
            return self._run_agency_cycle(user), None
        if mission.task_type == "software_patch":
            return self._run_software_patch(user, mission)
        raise ValueError(f"unsupported personal-agent task type: {mission.task_type}")

    def run(
        self,
        user: User,
        mission_id: str,
        *,
        trigger: str,
        only_if_due: bool = False,
    ) -> PersonalAgentMissionRun | None:
        now = datetime.utcnow()
        query = self.db.query(PersonalAgentMission).filter(
            PersonalAgentMission.mission_id == mission_id
        )
        try:
            query = query.with_for_update()
        except Exception:
            pass
        mission = query.one_or_none()
        if not mission:
            raise ValueError("personal-agent mission not found")
        if mission.user_id != user.id:
            raise ValueError("personal-agent mission does not belong to user")
        if mission.status != "active":
            if only_if_due:
                return None
            raise ValueError(f"personal-agent mission is {mission.status}")
        if only_if_due:
            if mission.trigger_type != "interval":
                return None
            if mission.next_run_at is None or mission.next_run_at > now:
                return None
        if mission.max_runs is not None and mission.run_count >= mission.max_runs:
            mission.status = "completed"
            mission.next_run_at = None
            mission.updated_at = now
            self.db.commit()
            return None

        mission.status = "running"
        mission.updated_at = now
        run = PersonalAgentMissionRun(
            run_id=uuid.uuid4().hex,
            mission_id=mission.id,
            trigger=trigger,
            status="running",
            external_dispatch=False,
            authorization_required=mission.task_type == "software_patch",
            started_at=now,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)

        try:
            result, software_agent_run_id = self._dispatch(user, mission)
            run.result = result
            run.software_agent_run_id = software_agent_run_id
            run.status = "succeeded"
            run.error = ""
            mission.last_result = result
            mission.last_error = ""
        except Exception as exc:
            message = str(exc)[:2000]
            run.status = "failed"
            run.error = message
            mission.last_error = message
            mission.last_result = {}
        finally:
            finished = datetime.utcnow()
            run.completed_at = finished
            mission.run_count += 1
            mission.last_run_at = finished
            mission.updated_at = finished
            if mission.max_runs is not None and mission.run_count >= mission.max_runs:
                mission.status = "completed"
                mission.next_run_at = None
            else:
                mission.status = "active"
                if mission.trigger_type == "interval":
                    mission.next_run_at = finished + timedelta(
                        seconds=mission.interval_seconds or 60
                    )
                else:
                    mission.next_run_at = None
            self.db.commit()
            self.db.refresh(run)
        return run

    def run_due(self, *, limit: int) -> list[dict[str, Any]]:
        now = datetime.utcnow()
        mission_ids = [
            row[0]
            for row in (
                self.db.query(PersonalAgentMission.mission_id)
                .filter(
                    PersonalAgentMission.status == "active",
                    PersonalAgentMission.trigger_type == "interval",
                    PersonalAgentMission.next_run_at.is_not(None),
                    PersonalAgentMission.next_run_at <= now,
                )
                .order_by(PersonalAgentMission.next_run_at.asc())
                .limit(limit)
                .all()
            )
        ]
        results: list[dict[str, Any]] = []
        for mission_id in mission_ids:
            mission = self.get(mission_id)
            user = self.db.query(User).filter(User.id == mission.user_id).one()
            run = self.run(user, mission_id, trigger="scheduler", only_if_due=True)
            if run is not None:
                results.append(
                    {
                        "mission_id": mission_id,
                        "run_id": run.run_id,
                        "status": run.status,
                    }
                )
        return results


class PersonalAgentRuntime:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._last_tick_at: float | None = None
        self._last_error = ""
        self._last_run_count = 0

    @property
    def enabled(self) -> bool:
        return settings.personal_agent_enabled

    def status(self) -> dict[str, Any]:
        with self._lock:
            age = None
            if self._last_tick_at is not None:
                age = max(0.0, time.monotonic() - self._last_tick_at)
            return {
                "runtime": "aura-personal-agent-v1",
                "enabled": self.enabled,
                "thread_alive": bool(self._thread and self._thread.is_alive()),
                "tick_seconds": settings.personal_agent_tick_seconds,
                "max_missions_per_tick": settings.personal_agent_max_missions_per_tick,
                "last_tick_age_seconds": age,
                "last_tick_run_count": self._last_run_count,
                "last_error": self._last_error,
            }

    def tick(self) -> list[dict[str, Any]]:
        db = SessionLocal()
        try:
            results = PersonalAgentService(db).run_due(
                limit=settings.personal_agent_max_missions_per_tick
            )
            with self._lock:
                self._last_tick_at = time.monotonic()
                self._last_run_count = len(results)
                self._last_error = ""
            return results
        except Exception as exc:
            with self._lock:
                self._last_tick_at = time.monotonic()
                self._last_run_count = 0
                self._last_error = str(exc)[:1000]
            return []
        finally:
            db.close()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.tick()
            if self._stop.wait(settings.personal_agent_tick_seconds):
                break

    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="aura-personal-agent-runtime",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._thread is None:
            return
        self._stop.set()
        self._thread.join(timeout=2)
        self._thread = None


personal_agent_runtime = PersonalAgentRuntime()
