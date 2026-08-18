from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from .config import settings
from .connectors.google import (
    GoogleReadOnlyConnector,
    finish_google_oauth,
    start_google_oauth,
)
from .db import Base, engine, get_db
from .models import ConnectorAccount, Intent, Opportunity, Outcome, Signal, User
from .routers.agency import router as agency_router
from .routers.future import router as future_router
from .routers.privacy import router as privacy_router
from .routers.state import router as state_router
from .routers.synthesis import router as synthesis_router
from .routers.world import router as world_router
from .schemas import (
    ConnectorStatusOut,
    IntentCreate,
    OpportunityOut,
    OutcomeCreate,
    SignalCreate,
    UserUpsert,
)
from .security import require_api_key
from .services.cycle import AgencyCycle
from .services.engine import OpportunityEngine
from .services.synthesis import SynthesisService
from .services.world_model import WorldModelService
from .world_schemas import EventCreate

settings.validate_runtime()
Base.metadata.create_all(bind=engine)
app = FastAPI(title="Human Agency Engine", version="0.7.0")
app.include_router(agency_router)
app.include_router(state_router)
app.include_router(future_router)
app.include_router(synthesis_router)
app.include_router(world_router)
app.include_router(privacy_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "human-agency-engine"}


@app.get("/ready")
def readiness(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(503, "database not ready") from exc
    return {"status": "ready", "database": "ok"}


@app.put("/v1/users/{external_id}", dependencies=[Depends(require_api_key)])
def upsert_user(
    external_id: str,
    payload: UserUpsert,
    db: Session = Depends(get_db),
):
    if external_id != payload.external_id:
        raise HTTPException(400, "external_id mismatch")

    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    created = user is None
    if user is None:
        user = User(**payload.model_dump())
        db.add(user)
    else:
        for key, value in payload.model_dump().items():
            setattr(user, key, value)

    db.commit()
    db.refresh(user)
    WorldModelService(db).append_event(
        user,
        EventCreate(
            event_type="user.created" if created else "user.profile_updated",
            source="api",
            subject_type="user",
            subject_id=str(user.id),
            payload={"country": user.country, "currency": user.currency, "timezone": user.timezone},
        ),
    )
    return {"id": user.id, "external_id": user.external_id}


@app.post(
    "/v1/users/{external_id}/intents",
    dependencies=[Depends(require_api_key)],
)
def add_intent(
    external_id: str,
    payload: IntentCreate,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")

    intent = Intent(user_id=user.id, **payload.model_dump())
    db.add(intent)
    db.commit()
    db.refresh(intent)
    WorldModelService(db).append_event(
        user,
        EventCreate(
            event_type="intent.created",
            source="user",
            subject_type="intent",
            subject_id=str(intent.id),
            payload={"kind": intent.kind, "priority": intent.priority, "active": intent.active},
        ),
    )
    return {"id": intent.id}


@app.post(
    "/v1/users/{external_id}/signals",
    dependencies=[Depends(require_api_key)],
)
def ingest_signal(
    external_id: str,
    payload: SignalCreate,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")

    data = payload.model_dump(exclude_none=True)
    if "observed_at" not in data:
        data["observed_at"] = datetime.utcnow()

    signal = Signal(user_id=user.id, **data)
    db.add(signal)
    db.commit()
    db.refresh(signal)
    WorldModelService(db).append_event(
        user,
        EventCreate(
            event_type="signal.observed",
            source=signal.source,
            subject_type="signal",
            subject_id=str(signal.id),
            payload={"signal_type": signal.type, "processed": signal.processed},
            occurred_at=signal.observed_at,
        ),
    )
    return {"id": signal.id, "processed": signal.processed}


@app.get(
    "/v1/users/{external_id}/connectors",
    response_model=list[ConnectorStatusOut],
    dependencies=[Depends(require_api_key)],
)
def list_connectors(external_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    return db.query(ConnectorAccount).filter(ConnectorAccount.user_id == user.id).all()


@app.post(
    "/v1/users/{external_id}/connectors/google/start",
    dependencies=[Depends(require_api_key)],
)
def google_oauth_start(external_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    try:
        return {"authorization_url": start_google_oauth(db, user)}
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get("/v1/connectors/google/callback")
def google_oauth_callback(
    state: str = Query(...),
    code: str = Query(...),
    db: Session = Depends(get_db),
):
    try:
        account = finish_google_oauth(db, state, code)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc

    return {
        "connected": True,
        "provider": account.provider,
        "scopes": account.scopes,
    }


@app.post(
    "/v1/users/{external_id}/connectors/google/sync",
    dependencies=[Depends(require_api_key)],
)
def sync_google(external_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    account = (
        db.query(ConnectorAccount)
        .filter(
            ConnectorAccount.user_id == user.id,
            ConnectorAccount.provider == "google",
            ConnectorAccount.enabled == True,  # noqa: E712
        )
        .one_or_none()
    )
    if not account:
        raise HTTPException(404, "Google connector not connected")
    try:
        sync_result = GoogleReadOnlyConnector(db).sync(account.id)
        opportunities = OpportunityEngine(db).run_for_user(user)
        synthesis = SynthesisService(db).run(user)
        return {
            **sync_result,
            "created_opportunities": len(opportunities),
            "synthesis": synthesis,
        }
    except Exception as exc:
        raise HTTPException(502, f"Google sync failed: {exc}") from exc


@app.delete(
    "/v1/users/{external_id}/connectors/google",
    dependencies=[Depends(require_api_key)],
)
def disable_google(external_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    account = (
        db.query(ConnectorAccount)
        .filter(
            ConnectorAccount.user_id == user.id,
            ConnectorAccount.provider == "google",
        )
        .one_or_none()
    )
    if not account:
        raise HTTPException(404, "Google connector not connected")
    account.enabled = False
    account.encrypted_token_json = ""
    account.last_error = ""
    account.updated_at = datetime.utcnow()
    db.commit()
    WorldModelService(db).append_event(
        user,
        EventCreate(
            event_type="connector.disconnected",
            source="user",
            subject_type="connector",
            subject_id=str(account.id),
            payload={"provider": "google"},
        ),
    )
    return {"disconnected": True, "provider": "google"}


@app.post("/v1/cycle/run", dependencies=[Depends(require_api_key)])
def run_cycle(db: Session = Depends(get_db)):
    return AgencyCycle(db).run()


@app.post(
    "/v1/users/{external_id}/engine/run",
    response_model=list[OpportunityOut],
    dependencies=[Depends(require_api_key)],
)
def run_engine(external_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    opportunities = OpportunityEngine(db).run_for_user(user)
    SynthesisService(db).run(user)
    return opportunities


@app.post("/v1/engine/run-all", dependencies=[Depends(require_api_key)])
def run_all(db: Session = Depends(get_db)):
    total_created = 0
    synthesis_totals = {
        "evaluated": 0,
        "ready_for_review": 0,
        "needs_information": 0,
        "rejected": 0,
        "queued_notifications": 0,
        "suppressed_notifications": 0,
    }
    engine_service = OpportunityEngine(db)
    synthesis_service = SynthesisService(db)
    for user in db.query(User).all():
        opportunities = engine_service.run_for_user(user)
        total_created += len(opportunities)
        result = synthesis_service.run(user)
        for key in synthesis_totals:
            synthesis_totals[key] += int(result.get(key, 0))
    return {"created_opportunities": total_created, "synthesis": synthesis_totals}


@app.get(
    "/v1/users/{external_id}/opportunities",
    response_model=list[OpportunityOut],
    dependencies=[Depends(require_api_key)],
)
def list_opportunities(external_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")

    return (
        db.query(Opportunity)
        .filter(Opportunity.user_id == user.id)
        .order_by(Opportunity.created_at.desc())
        .all()
    )


@app.put(
    "/v1/opportunities/{opportunity_id}/outcome",
    dependencies=[Depends(require_api_key)],
)
def record_outcome(
    opportunity_id: int,
    payload: OutcomeCreate,
    db: Session = Depends(get_db),
):
    opportunity = (
        db.query(Opportunity)
        .filter(Opportunity.id == opportunity_id)
        .one_or_none()
    )
    if not opportunity:
        raise HTTPException(404, "opportunity not found")

    outcome = (
        db.query(Outcome)
        .filter(Outcome.opportunity_id == opportunity_id)
        .one_or_none()
    )
    if outcome is None:
        outcome = Outcome(opportunity_id=opportunity_id, **payload.model_dump())
        db.add(outcome)
    else:
        for key, value in payload.model_dump().items():
            setattr(outcome, key, value)
        outcome.recorded_at = datetime.utcnow()

    if payload.executed is True:
        opportunity.status = "executed"
    elif payload.accepted is False:
        opportunity.status = "dismissed"
    elif payload.accepted is True:
        opportunity.status = "accepted"

    db.commit()
    db.refresh(outcome)
    user = db.query(User).filter(User.id == opportunity.user_id).one()
    WorldModelService(db).append_event(
        user,
        EventCreate(
            event_type="opportunity.outcome_recorded",
            source="user",
            subject_type="opportunity",
            subject_id=str(opportunity.id),
            payload={
                "status": opportunity.status,
                "useful": outcome.useful,
                "accepted": outcome.accepted,
                "executed": outcome.executed,
                "realized_value": outcome.realized_value,
            },
        ),
    )
    return {
        "opportunity_id": opportunity_id,
        "status": opportunity.status,
        "realized_value": outcome.realized_value,
        "useful": outcome.useful,
    }
