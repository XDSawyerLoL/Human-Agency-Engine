from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from .models import Intent, StateFact, User
from .schemas import IntentCreate, StateFactCreate, UserUpsert
from .security import require_api_key

# Import HORIZON routers explicitly. Importing the package also builds the legacy
# aggregate router for the historical application, but this dedicated app never
# mounts that aggregate router. Only the router objects listed here are exposed.
from .routers.horizon import router as horizon_router
from .routers.horizon_backfill import router as horizon_backfill_router
from .routers.horizon_backtest import router as horizon_backtest_router
from .routers.horizon_calibration import router as horizon_calibration_router
from .routers.horizon_cascade import router as horizon_cascade_router
from .routers.horizon_collector import router as horizon_collector_router
from .routers.horizon_convergence import router as horizon_convergence_router
from .routers.horizon_corpus import router as horizon_corpus_router
from .routers.horizon_emerging import router as horizon_emerging_router
from .routers.horizon_event_graph import router as horizon_event_graph_router
from .routers.horizon_expiry import router as horizon_expiry_router
from .routers.horizon_fuel import router as horizon_fuel_router
from .routers.horizon_global_alerts import router as horizon_global_alerts_router
from .routers.horizon_impact import router as horizon_impact_router
from .routers.horizon_live import router as horizon_live_router
from .routers.horizon_materialization import router as horizon_materialization_router
from .routers.horizon_media_attention import router as horizon_media_attention_router
from .routers.horizon_meteofrance import router as horizon_meteofrance_router
from .routers.horizon_normalizer import router as horizon_normalizer_router
from .routers.horizon_provisional import router as horizon_provisional_router
from .routers.horizon_reevaluation import router as horizon_reevaluation_router
from .routers.horizon_response_library import router as horizon_response_library_router
from .routers.horizon_sources import router as horizon_sources_router
from .routers.horizon_weather_chain import router as horizon_weather_chain_router
from .routers.horizon_windy import router as horizon_windy_router
from .config import settings


settings.validate_runtime()
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="HORIZON Predictive Intelligence API",
    version="1.2.0",
    description=(
        "Dedicated HORIZON surface: source intelligence, convergence, event graph, "
        "forecasting, historical replay, calibration corpus building and permanent collection. "
        "Legacy commerce/delegation routes are intentionally not mounted."
    ),
)

HORIZON_ROUTERS = (
    horizon_router,
    horizon_cascade_router,
    horizon_impact_router,
    horizon_sources_router,
    horizon_live_router,
    horizon_windy_router,
    horizon_meteofrance_router,
    horizon_normalizer_router,
    horizon_response_library_router,
    horizon_media_attention_router,
    horizon_fuel_router,
    horizon_reevaluation_router,
    horizon_emerging_router,
    horizon_provisional_router,
    horizon_materialization_router,
    horizon_expiry_router,
    horizon_calibration_router,
    horizon_backtest_router,
    horizon_backfill_router,
    horizon_weather_chain_router,
    horizon_global_alerts_router,
    horizon_convergence_router,
    horizon_event_graph_router,
    horizon_collector_router,
    horizon_corpus_router,
)

for router in HORIZON_ROUTERS:
    app.include_router(router, prefix="/v1")


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _user_or_404(db: Session, external_id: str) -> User:
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if user is None:
        raise HTTPException(404, "HORIZON user not found")
    return user


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "horizon-predictive-intelligence",
        "permanent_collector_supported": True,
        "calibration_corpus_builder_supported": True,
        "legacy_action_surface_exposed": False,
    }


@app.get("/ready")
def readiness(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(503, "database not ready") from exc
    return {"status": "ready", "database": "ok"}


@app.put(
    "/v1/horizon/context/users/{external_id}",
    dependencies=[Depends(require_api_key)],
)
def upsert_horizon_user(
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
    return {
        "id": user.id,
        "external_id": user.external_id,
        "country": user.country,
        "timezone": user.timezone,
        "created": created,
    }


@app.post(
    "/v1/horizon/context/users/{external_id}/state/facts",
    dependencies=[Depends(require_api_key)],
)
def add_horizon_state_fact(
    external_id: str,
    payload: StateFactCreate,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    data = payload.model_dump(exclude={"replace_current"}, exclude_none=True)
    observed_at = _utc_naive(data.get("observed_at") or datetime.utcnow())
    data["observed_at"] = observed_at
    expires_at = data.get("expires_at")
    if expires_at is not None:
        expires_at = _utc_naive(expires_at)
        if expires_at <= observed_at:
            raise HTTPException(400, "expires_at must be after observed_at")
        data["expires_at"] = expires_at

    if payload.replace_current:
        (
            db.query(StateFact)
            .filter(
                StateFact.user_id == user.id,
                StateFact.domain == payload.domain,
                StateFact.key == payload.key,
                StateFact.superseded == False,  # noqa: E712
            )
            .update({StateFact.superseded: True}, synchronize_session=False)
        )

    fact = StateFact(user_id=user.id, **data)
    db.add(fact)
    db.commit()
    db.refresh(fact)
    return {
        "id": fact.id,
        "domain": fact.domain,
        "key": fact.key,
        "value": fact.value,
        "confidence": fact.confidence,
        "observed_at": fact.observed_at,
        "expires_at": fact.expires_at,
        "superseded": fact.superseded,
    }


@app.post(
    "/v1/horizon/context/users/{external_id}/intents",
    dependencies=[Depends(require_api_key)],
)
def add_horizon_intent(
    external_id: str,
    payload: IntentCreate,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    intent = Intent(user_id=user.id, **payload.model_dump())
    db.add(intent)
    db.commit()
    db.refresh(intent)
    return {
        "id": intent.id,
        "kind": intent.kind,
        "statement": intent.statement,
        "priority": intent.priority,
        "active": intent.active,
        "created_at": intent.created_at,
    }
