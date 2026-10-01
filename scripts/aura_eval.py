#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "aura_eval" / "manifest.json"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            raw = line.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise SystemExit(f"{path}:{line_no}: each JSONL row must be an object")
            rows.append(row)
    return rows


def _manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    slots = data.get("slots")
    if not isinstance(slots, list) or len(slots) != 50:
        raise SystemExit("AURA-Eval manifest must contain exactly 50 slots")
    ids = [item.get("slot_id") for item in slots]
    if len(set(ids)) != len(ids) or any(not item for item in ids):
        raise SystemExit("AURA-Eval manifest slot IDs must be unique and non-empty")
    return data


def validate_holdout(manifest_path: Path, holdout_path: Path) -> dict[str, Any]:
    manifest = _manifest(manifest_path)
    expected = {item["slot_id"] for item in manifest["slots"]}
    required = {
        "slot_id",
        "mission",
        "initial_context",
        "perturbations",
        "success_criteria",
        "evaluator",
    }
    rows = _read_jsonl(holdout_path)
    seen: set[str] = set()
    errors: list[str] = []
    for index, row in enumerate(rows, 1):
        missing = sorted(required - row.keys())
        if missing:
            errors.append(f"row {index}: missing {', '.join(missing)}")
        slot_id = row.get("slot_id")
        if slot_id not in expected:
            errors.append(f"row {index}: unknown slot_id {slot_id!r}")
        if slot_id in seen:
            errors.append(f"row {index}: duplicate slot_id {slot_id!r}")
        if isinstance(slot_id, str):
            seen.add(slot_id)
    missing_slots = sorted(expected - seen)
    if missing_slots:
        errors.append("missing slots: " + ", ".join(missing_slots))
    if len(rows) != 50:
        errors.append(f"expected 50 holdout rows, found {len(rows)}")
    return {
        "valid": not errors,
        "benchmark": manifest["benchmark"],
        "version": manifest["version"],
        "row_count": len(rows),
        "errors": errors,
    }


def _number(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SystemExit(f"{row.get('slot_id', '?')}: {key} must be numeric")
    return float(value)


def score_results(manifest_path: Path, results_path: Path) -> dict[str, Any]:
    manifest = _manifest(manifest_path)
    expected = {item["slot_id"] for item in manifest["slots"]}
    rows = _read_jsonl(results_path)
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        slot_id = row.get("slot_id")
        if slot_id not in expected:
            raise SystemExit(f"unknown slot_id in results: {slot_id!r}")
        if slot_id in by_id:
            raise SystemExit(f"duplicate slot_id in results: {slot_id}")
        if not isinstance(row.get("success"), bool):
            raise SystemExit(f"{slot_id}: success must be boolean")
        quality = _number(row, "verified_quality")
        if quality is not None and not 0 <= quality <= 1:
            raise SystemExit(f"{slot_id}: verified_quality must be between 0 and 1")
        by_id[slot_id] = row

    values = list(by_id.values())
    success_count = sum(1 for row in values if row["success"])
    quality_values = [
        float(row["verified_quality"])
        for row in values
        if isinstance(row.get("verified_quality"), (int, float))
        and not isinstance(row.get("verified_quality"), bool)
    ]
    latencies = [v for row in values if (v := _number(row, "latency_s")) is not None]
    interventions = [v for row in values if (v := _number(row, "human_interventions")) is not None]
    energy_values = [v for row in values if (v := _number(row, "local_joules")) is not None]

    def total(key: str) -> float:
        return sum((_number(row, key) or 0.0) for row in values)

    mission_count = len(values)
    return {
        "benchmark": manifest["benchmark"],
        "version": manifest["version"],
        "mission_count": mission_count,
        "complete": set(by_id) == expected,
        "success_count": success_count,
        "success_rate": (success_count / mission_count) if mission_count else None,
        "verified_quality_mean": statistics.fmean(quality_values) if quality_values else None,
        "human_interventions_total": total("human_interventions"),
        "human_intervention_missions": sum(
            1 for row in values if (_number(row, "human_interventions") or 0) > 0
        ),
        "median_latency_s": statistics.median(latencies) if latencies else None,
        "model_calls_total": total("model_calls"),
        "tool_calls_total": total("tool_calls"),
        "tokens_in_total": total("tokens_in"),
        "tokens_out_total": total("tokens_out"),
        "local_joules_total": sum(energy_values) if energy_values else None,
        "local_joules_coverage": (len(energy_values) / mission_count) if mission_count else 0.0,
        "energy_scope": "local_measured_only",
        "remote_provider_energy": "unknown",
        "slot_ids": sorted(by_id),
    }


def compare_results(manifest_path: Path, baseline_path: Path, candidate_path: Path) -> dict[str, Any]:
    baseline = score_results(manifest_path, baseline_path)
    candidate = score_results(manifest_path, candidate_path)
    if baseline["slot_ids"] != candidate["slot_ids"]:
        raise SystemExit("baseline and candidate must contain the same slot IDs")

    energy_reduction_pct = None
    if (
        baseline["local_joules_coverage"] == 1.0
        and candidate["local_joules_coverage"] == 1.0
        and baseline["local_joules_total"]
        and baseline["local_joules_total"] > 0
        and candidate["local_joules_total"] is not None
    ):
        energy_reduction_pct = (
            1 - candidate["local_joules_total"] / baseline["local_joules_total"]
        ) * 100

    return {
        "benchmark": baseline["benchmark"],
        "version": baseline["version"],
        "same_missions": True,
        "baseline": baseline,
        "candidate": candidate,
        "delta": {
            "success_rate": (
                candidate["success_rate"] - baseline["success_rate"]
                if candidate["success_rate"] is not None and baseline["success_rate"] is not None
                else None
            ),
            "verified_quality_mean": (
                candidate["verified_quality_mean"] - baseline["verified_quality_mean"]
                if candidate["verified_quality_mean"] is not None
                and baseline["verified_quality_mean"] is not None
                else None
            ),
            "human_interventions_total": (
                candidate["human_interventions_total"] - baseline["human_interventions_total"]
            ),
            "median_latency_s": (
                candidate["median_latency_s"] - baseline["median_latency_s"]
                if candidate["median_latency_s"] is not None and baseline["median_latency_s"] is not None
                else None
            ),
            "local_energy_reduction_pct": energy_reduction_pct,
        },
        "energy_claim_allowed": energy_reduction_pct is not None,
        "note": (
            "Energy comparison covers measured local joules only. Remote provider energy remains unknown."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and score AURA-Eval holdout runs.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate-holdout")
    validate.add_argument("holdout", type=Path)

    score = sub.add_parser("score")
    score.add_argument("results", type=Path)

    compare = sub.add_parser("compare")
    compare.add_argument("baseline", type=Path)
    compare.add_argument("candidate", type=Path)

    args = parser.parse_args()
    if args.command == "validate-holdout":
        result = validate_holdout(args.manifest, args.holdout)
    elif args.command == "score":
        result = score_results(args.manifest, args.results)
    else:
        result = compare_results(args.manifest, args.baseline, args.candidate)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.command == "validate-holdout" and not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
