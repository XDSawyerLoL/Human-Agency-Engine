from __future__ import annotations

import json
from pathlib import Path

from app.services.aura_capability_registry import VALID_STATES, build_aura_capability_registry


ROOT = Path(__file__).resolve().parents[1]


def test_aura_capability_registry_is_explicit_and_unique():
    registry = build_aura_capability_registry()
    capabilities = registry["capabilities"]
    ids = [item["id"] for item in capabilities]

    assert len(ids) == len(set(ids))
    assert registry["summary"]["total"] == len(capabilities)
    assert all(item["state"] in VALID_STATES for item in capabilities)

    by_id = {item["id"]: item for item in capabilities}
    assert by_id["world_intelligence"]["state"] == "ACTIVE"
    assert by_id["browser_operator"]["state"] == "MISSING"
    assert by_id["computer_operator"]["state"] == "MISSING"
    assert by_id["conversation_continuity"]["state"] == "DEGRADED"
    assert by_id["aura_eval"]["state"] == "ACTIVE"
    assert by_id["energy_telemetry"]["state"] == "MISSING"


def test_aura_eval_manifest_has_fifty_blind_unique_slots():
    manifest = json.loads((ROOT / "aura_eval" / "manifest.json").read_text(encoding="utf-8"))
    slots = manifest["slots"]
    slot_ids = [item["slot_id"] for item in slots]

    assert manifest["slot_count"] == 50
    assert len(slots) == 50
    assert len(set(slot_ids)) == 50
    assert all(item["blind"] is True for item in slots)
    assert all(item["instance"] == "external_holdout_required" for item in slots)


def test_aura_eval_covers_ten_families_with_five_slots_each():
    manifest = json.loads((ROOT / "aura_eval" / "manifest.json").read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    for slot in manifest["slots"]:
        counts[slot["family"]] = counts.get(slot["family"], 0) + 1

    assert len(counts) == 10
    assert set(counts.values()) == {5}
