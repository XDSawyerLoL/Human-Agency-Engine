from __future__ import annotations

from typing import Any


def _nested(value: Any, path: str) -> Any:
    current = value
    if not path:
        return current
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def evaluate_personal_scope(state_snapshot: dict, personal_scope: dict | None) -> dict:
    if not isinstance(personal_scope, dict) or not personal_scope:
        return {
            "configured": False,
            "status": "unscoped",
            "score": 0.5,
            "rules": [],
        }

    rules = personal_scope.get("all", [])
    if not isinstance(rules, list) or not rules:
        return {
            "configured": True,
            "status": "unknown",
            "score": 0.25,
            "rules": [],
            "reason": "personal_scope contains no supported all-rules",
        }

    results = []
    any_unknown = False
    any_mismatch = False
    for raw in rules:
        if not isinstance(raw, dict):
            any_unknown = True
            results.append({"status": "unknown", "reason": "invalid rule"})
            continue
        state_key = str(raw.get("state_key") or "").strip()
        value_path = str(raw.get("value_path") or "").strip()
        operator = str(raw.get("operator") or "equals").strip().lower()
        state_item = state_snapshot.get(state_key)
        if not isinstance(state_item, dict) or "value" not in state_item:
            any_unknown = True
            results.append({
                "state_key": state_key,
                "value_path": value_path,
                "operator": operator,
                "status": "unknown",
                "reason": "required personal state is missing",
            })
            continue
        actual = _nested(state_item.get("value"), value_path)
        if actual is None:
            any_unknown = True
            results.append({
                "state_key": state_key,
                "value_path": value_path,
                "operator": operator,
                "status": "unknown",
                "reason": "required value path is missing",
            })
            continue

        if operator == "equals":
            expected = raw.get("value")
            matched = str(actual).upper() == str(expected).upper()
        elif operator == "in":
            expected_values = raw.get("values", [])
            if not isinstance(expected_values, list):
                any_unknown = True
                results.append({
                    "state_key": state_key,
                    "value_path": value_path,
                    "operator": operator,
                    "status": "unknown",
                    "reason": "in operator requires values list",
                })
                continue
            matched = str(actual).upper() in {str(item).upper() for item in expected_values}
            expected = expected_values
        else:
            any_unknown = True
            results.append({
                "state_key": state_key,
                "value_path": value_path,
                "operator": operator,
                "status": "unknown",
                "reason": "unsupported operator",
            })
            continue

        if not matched:
            any_mismatch = True
        results.append({
            "state_key": state_key,
            "value_path": value_path,
            "operator": operator,
            "expected": expected,
            "actual": actual,
            "status": "matched" if matched else "mismatched",
        })

    if any_mismatch:
        status = "mismatched"
        score = 0.0
    elif any_unknown:
        status = "unknown"
        score = 0.25
    else:
        status = "matched"
        score = 1.0
    return {
        "configured": True,
        "status": status,
        "score": score,
        "rules": results,
    }
