from types import SimpleNamespace

from app.services.intent_matcher import best_intent_match


def test_best_intent_match_uses_statement_and_target_keywords():
    intent = SimpleNamespace(
        statement="Changer de métier vers l'innovation",
        target={"keywords": ["formation", "digital", "innovation"]},
        priority=0.9,
    )
    matched, score = best_intent_match(
        "Inscription formation innovation digitale avant vendredi",
        [intent],
    )
    assert matched is intent
    assert score > 0.2
