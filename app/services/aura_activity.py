from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import Intent, User
from ..personal_agent_models import PersonalAgentMission
from .personal_agent import personal_agent_runtime


class AuraActivityService:
    """Read-only source of truth for AURA's current work and intentions.

    This service deliberately never decrypts mission goals or task payloads.
    It is designed for the dialogue layer to answer questions such as
    "what are you working on?" from persisted runtime state instead of an LLM
    improvising an answer.
    """

    def __init__(self, db: Session):
        self.db = db

    def snapshot(self, user: User) -> dict[str, Any]:
        intents = (
            self.db.query(Intent)
            .filter(Intent.user_id == user.id, Intent.active == True)  # noqa: E712
            .order_by(Intent.priority.desc(), Intent.created_at.asc())
            .limit(20)
            .all()
        )
        missions = (
            self.db.query(PersonalAgentMission)
            .filter(
                PersonalAgentMission.user_id == user.id,
                PersonalAgentMission.status.in_(("active", "running", "paused")),
            )
            .order_by(PersonalAgentMission.updated_at.desc())
            .limit(20)
            .all()
        )

        running = [item for item in missions if item.status == "running"]
        active = [item for item in missions if item.status == "active"]
        paused = [item for item in missions if item.status == "paused"]

        if running:
            mode = "working"
            focus = running[0].title
        elif active:
            mode = "scheduled"
            focus = active[0].title
        elif intents:
            mode = "intent_only"
            focus = intents[0].statement
        else:
            mode = "idle"
            focus = None

        return {
            "source": "persisted_aura_state",
            "mode": mode,
            "focus": focus,
            "runtime": personal_agent_runtime.status(),
            "missions": [
                {
                    "mission_id": item.mission_id,
                    "title": item.title,
                    "task_type": item.task_type,
                    "autonomy_level": item.autonomy_level,
                    "status": item.status,
                    "run_count": item.run_count,
                    "max_runs": item.max_runs,
                    "next_run_at": item.next_run_at,
                    "last_run_at": item.last_run_at,
                    "last_error": item.last_error,
                    "updated_at": item.updated_at,
                }
                for item in missions
            ],
            "intents": [
                {
                    "id": item.id,
                    "kind": item.kind,
                    "statement": item.statement,
                    "priority": item.priority,
                    "created_at": item.created_at,
                }
                for item in intents
            ],
            "counts": {
                "running_missions": len(running),
                "active_missions": len(active),
                "paused_missions": len(paused),
                "active_intents": len(intents),
            },
            "dialogue_instruction": (
                "Answer current-work questions from this persisted state. "
                "Do not invent work that is not represented here."
            ),
        }
