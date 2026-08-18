from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from .models import Intent, Opportunity, Signal, User
from .schemas import IntentCreate, OpportunityOut, SignalCreate, UserUpsert
from .security import require_api_key
from .services.engine import OpportunityEngine

Base.metadata.create_all(bind=engine)
app = FastAPI(title="Human Agency Engine", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok", "service": "human-agency-engine"}


@app.put("/v1/users/{external_id}", dependencies=[Depends(require_api_key)])
def upsert_user(
    external_id: str,
    payload: UserUpsert,
    db: Session = Depends(get_db),
):
    if external_id != payload.external_id:
        raise HTTPException(400, "external_id mismatch")

    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if user is None:
        user = User(**payload.model_dump())
        db.add(user)
    else:
        for key, value in payload.model_dump().items():
            setattr(user, key, value)

    db.commit()
    db.refresh(user)
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
    return {"id": signal.id, "processed": signal.processed}


@app.post(
    "/v1/users/{external_id}/engine/run",
    response_model=list[OpportunityOut],
    dependencies=[Depends(require_api_key)],
)
def run_engine(external_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    return OpportunityEngine(db).run_for_user(user)


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
