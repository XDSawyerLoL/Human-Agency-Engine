from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi.encoders import jsonable_encoder

from app.db import SessionLocal
from app.services.horizon_collector import HorizonCollectorService
from app.services.horizon_world_patterns import HorizonWorldPatternService


STATUS_PATH = Path(os.getenv("HORIZON_GITHUB_STATUS_PATH", "horizon-github-status.json"))


def main() -> None:
    run_id = os.getenv("GITHUB_RUN_ID", "local")
    run_attempt = os.getenv("GITHUB_RUN_ATTEMPT", "1")
    owner_id = os.getenv(
        "HORIZON_COLLECTOR_OWNER_ID",
        f"github-actions:{run_id}:{run_attempt}",
    )

    db = SessionLocal()
    try:
        world_pattern_ids = HorizonWorldPatternService(db).sync()
        service = HorizonCollectorService(db)
        cycle = service.run_due(
            owner_id=owner_id,
            trigger="github-actions-fallback",
        )
        status = service.status(cycle_limit=5)
        payload = {
            "mode": "github-only-fallback",
            "run_id": run_id,
            "run_attempt": run_attempt,
            "owner_id": owner_id,
            "world_pattern_ids": world_pattern_ids,
            "cycle": jsonable_encoder(cycle),
            "collector": jsonable_encoder(status),
            "critical_semantics": {
                "ephemeral_runner": True,
                "state_restored_from_actions_artifact": True,
                "public_world_evidence_only": True,
                "personal_data_allowed": False,
                "github_actions_is_not_permanent_hosting": True,
                "world_pulse_patterns_synced": True,
                "numeric_probabilities_enabled": False,
            },
        }
        STATUS_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
