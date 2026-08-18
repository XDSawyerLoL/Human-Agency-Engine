from __future__ import annotations

import json
import re
import unicodedata

from ..models import Intent

STOPWORDS = {
    "a", "au", "aux", "avec", "ce", "ces", "de", "des", "du", "en", "et", "je",
    "la", "le", "les", "ma", "mes", "mon", "pour", "que", "qui", "sur", "un", "une",
    "the", "to", "and", "of", "for", "my", "in", "on", "with", "an", "is",
}


def _normalize(value: str) -> set[str]:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    tokens = re.findall(r"[a-z0-9]{3,}", value.lower())
    return {token for token in tokens if token not in STOPWORDS}


def intent_text(intent: Intent) -> str:
    return f"{intent.statement} {json.dumps(intent.target, ensure_ascii=False, default=str)}"


def best_intent_match(text: str, intents: list[Intent]) -> tuple[Intent | None, float]:
    observed = _normalize(text)
    if not observed:
        return None, 0.0

    best: Intent | None = None
    best_score = 0.0

    for intent in intents:
        expected = _normalize(intent_text(intent))
        if not expected:
            continue
        intersection = len(observed & expected)
        lexical = intersection / max(1, min(len(expected), 8))
        weighted = min(1.0, lexical * (0.65 + 0.35 * intent.priority))
        if weighted > best_score:
            best = intent
            best_score = weighted

    return best, best_score
