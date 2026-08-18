from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from ..models import Notification, Opportunity, PersonalMandate, User


DEFAULT_POLICY = {
    "min_confidence": 0.72,
    "max_per_day": 3,
    "category_cooldown_hours": 24,
    "quiet_hours": {"start": 22, "end": 7},
}


class ProactivityService:
    """Decides whether an opportunity deserves the user's attention.

    Suppressed notifications are persisted too. Silence must remain auditable.
    """

    def __init__(self, db: Session):
        self.db = db

    def evaluate(self, user: User, opportunity: Opportunity) -> Notification:
        existing = (
            self.db.query(Notification)
            .filter(Notification.opportunity_id == opportunity.id)
            .one_or_none()
        )
        if existing:
            return existing

        policy = self._policy_for(user)
        reason = self._suppression_reason(user, opportunity, policy)
        available_at = self._available_at(user, policy)

        notification = Notification(
            user_id=user.id,
            opportunity_id=opportunity.id,
            channel="in_app",
            title=opportunity.title,
            body=opportunity.rationale,
            status="suppressed" if reason else "queued",
            suppression_reason=reason,
            priority=max(0.0, min(1.0, opportunity.confidence)),
            available_at=available_at,
        )
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)
        return notification

    def evaluate_many(self, user: User, opportunities: list[Opportunity]) -> list[Notification]:
        return [self.evaluate(user, opportunity) for opportunity in opportunities]

    def _policy_for(self, user: User) -> dict:
        mandate = (
            self.db.query(PersonalMandate)
            .filter(PersonalMandate.user_id == user.id)
            .one_or_none()
        )
        policy = dict(DEFAULT_POLICY)
        if mandate and isinstance(mandate.notification_policy, dict):
            policy.update(mandate.notification_policy)
        return policy

    def _suppression_reason(self, user: User, opportunity: Opportunity, policy: dict) -> str:
        if opportunity.care_status == "blocked":
            return "CARE blocked this opportunity"

        min_confidence = float(policy.get("min_confidence", DEFAULT_POLICY["min_confidence"]))
        if opportunity.confidence < min_confidence:
            return f"confidence below proactive threshold ({opportunity.confidence:.2f} < {min_confidence:.2f})"

        mandate = (
            self.db.query(PersonalMandate)
            .filter(PersonalMandate.user_id == user.id)
            .one_or_none()
        )
        if mandate:
            never_notify = mandate.constraints.get("never_notify_categories", []) if isinstance(mandate.constraints, dict) else []
            if opportunity.category in never_notify:
                return f"category '{opportunity.category}' is muted by the personal mandate"

        now = datetime.utcnow()
        day_start = self._local_day_start_utc(user, now)
        sent_today = (
            self.db.query(Notification)
            .filter(
                Notification.user_id == user.id,
                Notification.created_at >= day_start,
                Notification.status.in_(["queued", "delivered"]),
            )
            .count()
        )
        max_per_day = max(0, int(policy.get("max_per_day", DEFAULT_POLICY["max_per_day"])))
        if sent_today >= max_per_day:
            return f"daily proactive limit reached ({max_per_day})"

        cooldown_hours = max(0, int(policy.get("category_cooldown_hours", DEFAULT_POLICY["category_cooldown_hours"])))
        if cooldown_hours:
            cutoff = now - timedelta(hours=cooldown_hours)
            recent_same_category = (
                self.db.query(Notification)
                .join(Opportunity, Notification.opportunity_id == Opportunity.id)
                .filter(
                    Notification.user_id == user.id,
                    Notification.created_at >= cutoff,
                    Notification.status.in_(["queued", "delivered"]),
                    Opportunity.category == opportunity.category,
                )
                .first()
            )
            if recent_same_category:
                return f"category cooldown active ({cooldown_hours}h)"

        return ""

    def _zone(self, user: User) -> ZoneInfo:
        try:
            return ZoneInfo(user.timezone)
        except ZoneInfoNotFoundError:
            return ZoneInfo("UTC")

    def _local_day_start_utc(self, user: User, now_utc_naive: datetime) -> datetime:
        zone = self._zone(user)
        aware = now_utc_naive.replace(tzinfo=timezone.utc).astimezone(zone)
        local_start = aware.replace(hour=0, minute=0, second=0, microsecond=0)
        return local_start.astimezone(timezone.utc).replace(tzinfo=None)

    def _available_at(self, user: User, policy: dict) -> datetime:
        now = datetime.now(timezone.utc)
        quiet = policy.get("quiet_hours") or {}
        try:
            start = int(quiet.get("start", DEFAULT_POLICY["quiet_hours"]["start"])) % 24
            end = int(quiet.get("end", DEFAULT_POLICY["quiet_hours"]["end"])) % 24
        except (TypeError, ValueError):
            return now.replace(tzinfo=None)

        zone = self._zone(user)
        local = now.astimezone(zone)
        hour = local.hour
        in_quiet = (start < end and start <= hour < end) or (start > end and (hour >= start or hour < end))
        if not in_quiet:
            return now.replace(tzinfo=None)

        target = local.replace(hour=end, minute=0, second=0, microsecond=0)
        if start > end and hour >= start:
            target += timedelta(days=1)
        elif start < end and target <= local:
            target += timedelta(days=1)
        return target.astimezone(timezone.utc).replace(tzinfo=None)
