from __future__ import annotations

import json

from app.db import SessionLocal
from app.services.horizon_health_patterns import HorizonHealthPatternService
from app.services.horizon_response_library import HorizonResponseLibraryService
from app.services.horizon_sources import HorizonSourceService
from app.services.horizon_statistical_patterns import HorizonStatisticalPatternService
from app.services.horizon_world_patterns import HorizonWorldPatternService


def main() -> None:
    db = SessionLocal()
    try:
        payload = {
            "service": "horizon-hostinger-init",
            "source_registry": HorizonSourceService(db).sync_builtin_sources(),
            "response_library": HorizonResponseLibraryService(db).sync_builtins(),
            "world_pattern_ids": HorizonWorldPatternService(db).sync(),
            "health_pattern_id": HorizonHealthPatternService(db).sync(),
            "statistical_pattern_ids": HorizonStatisticalPatternService(db).sync(),
            "status": "ready",
        }
        print(json.dumps(payload, ensure_ascii=False, default=str), flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
