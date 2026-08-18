from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from ..models import Intent, Opportunity, Signal, User
from .care import evaluate_financial_care
from .intent_matcher import best_intent_match

TIME_SENSITIVE_TERMS = {
    "deadline", "due", "expires", "expiry", "closing", "renewal", "renew",
    "echeance", "échéance", "expire", "expiration", "inscription", "candidature",
    "dernier delai", "dernier délai", "avant le", "rendez-vous", "appointment",
}


def _days_until(value: str | None) -> int | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo:
            now = datetime.now(timezone.utc)
            return (parsed.astimezone(timezone.utc).date() - now.date()).days
        return (parsed.date() - date.today()).days
    except ValueError:
        try:
            return (date.fromisoformat(value) - date.today()).days
        except ValueError:
            return None


class OpportunityEngine:
    def __init__(self, db: Session):
        self.db = db

    def run_for_user(self, user: User) -> list[Opportunity]:
        signals = (
            self.db.query(Signal)
            .filter(Signal.user_id == user.id, Signal.processed == False)  # noqa: E712
            .all()
        )
        intents = (
            self.db.query(Intent)
            .filter(Intent.user_id == user.id, Intent.active == True)  # noqa: E712
            .all()
        )

        created: list[Opportunity] = []
        for signal in signals:
            opportunity = self._from_signal(user, signal, intents)
            signal.processed = True
            if opportunity:
                self.db.add(opportunity)
                created.append(opportunity)

        self.db.commit()
        for item in created:
            self.db.refresh(item)
        return created

    def _from_signal(
        self, user: User, signal: Signal, intents: list[Intent]
    ) -> Opportunity | None:
        payload = signal.payload

        if signal.type == "recurring_expense":
            amount = float(payload.get("monthly_amount", 0))
            usage = float(payload.get("usage_score", 1))
            if amount <= 0 or usage > 0.35:
                return None

            annual = amount * 12
            care, reason = evaluate_financial_care(
                cash=user.liquid_cash,
                buffer=user.minimum_cash_buffer,
            )
            return Opportunity(
                user_id=user.id,
                signal_id=signal.id,
                category="money",
                title=f"Potentially recover {amount:.2f} {user.currency}/month",
                rationale="Recurring expense appears weakly used compared with its monthly cost.",
                proposed_action={
                    "type": "review_subscription",
                    "merchant": payload.get("merchant"),
                    "monthly_amount": amount,
                },
                baseline={"annual_cost": annual},
                counterfactual={"annual_cost": 0, "annual_delta": annual},
                expected_value=annual,
                confidence=min(0.95, 0.65 + (0.35 - usage)),
                care_status=care,
                care_reason=reason,
            )

        if signal.type == "price_drop":
            current = float(payload.get("current_price", 0))
            previous = float(payload.get("reference_price", 0))
            label = str(payload.get("label", "tracked item"))
            matched = [
                intent
                for intent in intents
                if intent.kind == "purchase"
                and label.lower() in intent.statement.lower()
            ]
            if not matched or current <= 0 or previous <= current:
                return None

            drop = previous - current
            care, reason = evaluate_financial_care(
                cash=user.liquid_cash,
                buffer=user.minimum_cash_buffer,
                immediate_cost=current,
            )
            return Opportunity(
                user_id=user.id,
                signal_id=signal.id,
                category="purchase",
                title=f"Tracked purchase dropped by {drop:.2f} {user.currency}",
                rationale="A product tied to an active purchase intention moved below its reference price.",
                proposed_action={
                    "type": "consider_purchase",
                    "label": label,
                    "price": current,
                    "url": payload.get("url"),
                },
                baseline={"buy_later_estimate": previous},
                counterfactual={
                    "buy_now": current,
                    "savings_vs_reference": drop,
                },
                expected_value=drop,
                confidence=0.82,
                care_status=care,
                care_reason=reason,
            )

        if signal.type == "deadline":
            days = int(payload.get("days_remaining", 999))
            relevance = float(payload.get("relevance", 0.0))
            if days < 0 or days > 14 or relevance < 0.6:
                return None

            return Opportunity(
                user_id=user.id,
                signal_id=signal.id,
                category="timing",
                title=f"Relevant deadline in {days} day(s)",
                rationale=str(
                    payload.get(
                        "reason",
                        "An active intention may be affected by an approaching deadline.",
                    )
                ),
                proposed_action={
                    "type": "review_deadline",
                    "label": payload.get("label"),
                    "deadline": payload.get("deadline"),
                },
                baseline={"if_ignored": "opportunity may expire"},
                counterfactual={"if_reviewed": "preserves option value"},
                expected_value=relevance * 100,
                confidence=min(0.9, 0.55 + relevance / 3),
                care_status="approved",
                care_reason="non-financial review only",
            )

        if signal.type == "calendar_event":
            text = " ".join(
                str(payload.get(key, ""))
                for key in ("summary", "description", "location")
            )
            intent, match_score = best_intent_match(text, intents)
            days = _days_until(payload.get("start"))
            if intent is None or days is None or days < 0 or days > 14 or match_score < 0.2:
                return None

            confidence = min(0.9, 0.55 + match_score * 0.35)
            return Opportunity(
                user_id=user.id,
                signal_id=signal.id,
                category="timing",
                title=f"Upcoming event may affect: {intent.statement[:120]}",
                rationale=(
                    f"An event in {days} day(s) matches an active intention. "
                    "Reviewing it now may preserve time and options."
                ),
                proposed_action={
                    "type": "review_calendar_event",
                    "event_id": payload.get("event_id"),
                    "summary": payload.get("summary"),
                    "start": payload.get("start"),
                    "url": payload.get("html_link"),
                },
                baseline={"if_ignored": "less preparation time"},
                counterfactual={"if_reviewed": "earlier preparation and preserved optionality"},
                expected_value=50 + 50 * intent.priority,
                confidence=confidence,
                care_status="approved",
                care_reason="read-only calendar review; no action is executed",
            )

        if signal.type == "email_message":
            text = " ".join(
                str(payload.get(key, ""))
                for key in ("subject", "sender", "snippet")
            )
            lower = text.lower()
            urgent = any(term in lower for term in TIME_SENSITIVE_TERMS)
            intent, match_score = best_intent_match(text, intents)
            if not urgent or intent is None or match_score < 0.2:
                return None

            confidence = min(0.86, 0.5 + match_score * 0.35)
            return Opportunity(
                user_id=user.id,
                signal_id=signal.id,
                category="timing",
                title=f"Time-sensitive email may affect: {intent.statement[:120]}",
                rationale=(
                    "A newly observed email contains time-sensitive language and "
                    "matches an active intention. The engine is surfacing it for review, "
                    "not acting on it."
                ),
                proposed_action={
                    "type": "review_email",
                    "message_id": payload.get("message_id"),
                    "subject": payload.get("subject"),
                    "sender": payload.get("sender"),
                },
                baseline={"if_ignored": "possible loss of timing or option value"},
                counterfactual={"if_reviewed": "user can decide before the window closes"},
                expected_value=45 + 55 * intent.priority,
                confidence=confidence,
                care_status="approved",
                care_reason="read-only email review; message content is not sent or modified",
            )

        return None
