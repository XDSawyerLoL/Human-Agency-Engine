from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.horizon_source_schemas import HorizonSourceUpsert
from app.main import app
from app.services.horizon_sources import HorizonSourceService


client = TestClient(app)


def _payload(key: str, *, enabled: bool) -> dict:
    return {
        "source_key": key,
        "name": "Synthetic governed source",
        "source_class": "official_statistical",
        "adapter_kind": "synthetic_governed",
        "domains": ["test"],
        "geography": ["FR"],
        "base_locator": "https://example.invalid/governed",
        "trust_weight": 0.8,
        "refresh_seconds": 900,
        "requires_credentials": False,
        "enabled": enabled,
        "metadata_json": {"role": "test"},
    }


def test_internal_adapter_sync_preserves_disabled_state_but_admin_route_can_change_it():
    db = SessionLocal()
    key = f"governed-{uuid4().hex[:10]}"
    try:
        service = HorizonSourceService(db)
        created = service.upsert_source(HorizonSourceUpsert(**_payload(key, enabled=True)))
        assert created.enabled is True

        disabled = client.put("/v1/horizon/sources", json=_payload(key, enabled=False))
        assert disabled.status_code == 200, disabled.text
        assert disabled.json()["enabled"] is False

        # The protected admin request used another DB session; expire the local
        # identity map so this simulates the next adapter cycle reading committed state.
        db.expire_all()
        internal_sync = service.upsert_source(HorizonSourceUpsert(**_payload(key, enabled=True)))
        assert internal_sync.enabled is False

        enabled = client.put("/v1/horizon/sources", json=_payload(key, enabled=True))
        assert enabled.status_code == 200, enabled.text
        assert enabled.json()["enabled"] is True
    finally:
        db.close()
