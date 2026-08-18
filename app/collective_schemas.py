from pydantic import BaseModel


class CollectiveIntentJoin(BaseModel):
    envelope_id: str
    confirm: str


class CollectiveIntentLeave(BaseModel):
    confirm: str
