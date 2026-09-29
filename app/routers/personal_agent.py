from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..personal_agent_models import PersonalAgentMission, PersonalAgentMissionRun
from ..personal_agent_schemas import (
    PersonalAgentMissionControl,
    PersonalAgentMissionCreate,
    PersonalAgentRunRequest,
)
from ..security import require_api_key
from ..services.personal_agent import PersonalAgentService, personal_agent_runtime


router = APIRouter(
    prefix="/personal-agent",
    dependencies=[Depends(require_api_key)],
)


def _user_or_404(db: Session, external_id: str) -> User:
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    return user


def _mission_out(item: PersonalAgentMission) -> dict:
    return {
        "mission_id": item.mission_id,
        "title": item.title,
        "goal_hash": item.goal_hash,
        "goal_persisted": "encrypted",
        "task_type": item.task_type,
        "autonomy_level": item.autonomy_level,
        "required_capabilities": item.required_capabilities,
        "task_payload_persisted": "encrypted",
        "trigger_type": item.trigger_type,
        "interval_seconds": item.interval_seconds,
        "status": item.status,
        "run_count": item.run_count,
        "max_runs": item.max_runs,
        "next_run_at": item.next_run_at,
        "last_run_at": item.last_run_at,
        "last_result": item.last_result,
        "last_error": item.last_error,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _run_out(item: PersonalAgentMissionRun) -> dict:
    return {
        "run_id": item.run_id,
        "trigger": item.trigger,
        "status": item.status,
        "result": item.result,
        "error": item.error,
        "external_dispatch": item.external_dispatch,
        "authorization_required": item.authorization_required,
        "software_agent_run_id": item.software_agent_run_id,
        "started_at": item.started_at,
        "completed_at": item.completed_at,
    }


@router.get("/runtime")
def runtime_status():
    return personal_agent_runtime.status()


@router.get("/users/{external_id}/capabilities")
def capabilities(external_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    return PersonalAgentService(db).capabilities(user)


@router.post("/users/{external_id}/missions")
def create_mission(
    external_id: str,
    payload: PersonalAgentMissionCreate,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    try:
        mission = PersonalAgentService(db).create(user, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _mission_out(mission)


@router.get("/users/{external_id}/missions")
def list_missions(external_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    return [_mission_out(item) for item in PersonalAgentService(db).list_for_user(user)]


@router.get("/users/{external_id}/missions/{mission_id}")
def get_mission(external_id: str, mission_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    try:
        mission = PersonalAgentService(db).get(mission_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    if mission.user_id != user.id:
        raise HTTPException(404, "personal-agent mission not found")
    return _mission_out(mission)


@router.get("/users/{external_id}/missions/{mission_id}/runs")
def list_mission_runs(external_id: str, mission_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    service = PersonalAgentService(db)
    try:
        mission = service.get(mission_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    if mission.user_id != user.id:
        raise HTTPException(404, "personal-agent mission not found")
    return [_run_out(item) for item in service.list_runs(mission)]


@router.post("/users/{external_id}/missions/{mission_id}/run")
def run_mission(
    external_id: str,
    mission_id: str,
    payload: PersonalAgentRunRequest,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    try:
        run = PersonalAgentService(db).run(
            user,
            mission_id,
            trigger=payload.trigger,
            only_if_due=False,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if run is None:
        raise HTTPException(409, "personal-agent mission did not run")
    return _run_out(run)


@router.post("/users/{external_id}/missions/{mission_id}/pause")
def pause_mission(
    external_id: str,
    mission_id: str,
    payload: PersonalAgentMissionControl,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    try:
        return _mission_out(PersonalAgentService(db).pause(user, mission_id, payload.reason))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/users/{external_id}/missions/{mission_id}/resume")
def resume_mission(external_id: str, mission_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    try:
        return _mission_out(PersonalAgentService(db).resume(user, mission_id))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/users/{external_id}/missions/{mission_id}/cancel")
def cancel_mission(
    external_id: str,
    mission_id: str,
    payload: PersonalAgentMissionControl,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    try:
        return _mission_out(PersonalAgentService(db).cancel(user, mission_id, payload.reason))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
