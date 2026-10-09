"""Read side of moderation: what is hidden, and what a moderator still has to look at."""

from dataclasses import dataclass
from typing import Any

from django.db.models import Exists, OuterRef, QuerySet, Subquery

from apps.contributions.models import FraudSeverity, FraudSignal
from apps.prices.models import PriceObservation

from .models import ModerationAction, PriceAppeal, PriceModeration

VISIBLE = "VISIBLE"
HIDDEN = "HIDDEN"
APPEAL_PENDING = "APPEAL_PENDING"
UPHELD = "UPHELD"  # hidden for good: the appeal was refused


@dataclass(frozen=True)
class ModerationState:
    state: str
    reason: str = ""
    hide_id: Any = None  # the HIDE decision an appeal would contest

    @property
    def hidden(self) -> bool:
        return self.state != VISIBLE

    @property
    def can_appeal(self) -> bool:
        return self.state == HIDDEN


def _latest(observation_id: Any) -> PriceModeration | None:
    return PriceModeration.objects.filter(observation_id=observation_id).first()


def state_of(observation_id: Any) -> ModerationState:
    latest = _latest(observation_id)
    if latest is None or latest.action == ModerationAction.RESTORE:
        return ModerationState(VISIBLE)
    if latest.action == ModerationAction.UPHOLD:
        return ModerationState(UPHELD, reason=latest.reason)
    appeal = PriceAppeal.objects.filter(moderation=latest).exists()
    return ModerationState(
        APPEAL_PENDING if appeal else HIDDEN, reason=latest.reason, hide_id=latest.pk
    )


def exclude_hidden(queryset: QuerySet[PriceObservation]) -> QuerySet[PriceObservation]:
    """Drop observations whose latest moderation decision keeps them hidden."""
    latest_action = (
        PriceModeration.objects.filter(observation=OuterRef("pk"))
        .order_by("-created_at")
        .values("action")[:1]
    )
    hidden = PriceObservation.objects.filter(
        pk=OuterRef("pk"),
    ).annotate(latest=Subquery(latest_action))
    hidden = hidden.filter(latest__in=[ModerationAction.HIDE, ModerationAction.UPHOLD])
    return queryset.exclude(Exists(hidden))


_SEVERITY_ORDER: dict[str, int] = {
    FraudSeverity.HIGH.value: 0,
    FraudSeverity.MEDIUM.value: 1,
    FraudSeverity.LOW.value: 2,
}


def pending_signals(limit: int = 50) -> list[FraudSignal]:
    """Signals nobody reviewed yet, most serious first, then oldest first."""
    rows = list(
        FraudSignal.objects.filter(review__isnull=True)
        .select_related(
            "contribution__store",
            "contribution__observation__product_variant__product",
        )
        .order_by("created_at")[:500]
    )
    rows.sort(key=lambda s: _SEVERITY_ORDER.get(s.severity, 3))
    return rows[:limit]


def pending_appeals(limit: int = 50) -> list[PriceAppeal]:
    """Appeals whose HIDE is still the latest decision (nobody answered yet)."""
    pending = []
    for appeal in PriceAppeal.objects.select_related(
        "moderation__observation__store", "moderation__observation__product_variant__product"
    ).order_by("created_at")[:500]:
        latest = _latest(appeal.moderation.observation_id)
        if latest is not None and latest.pk == appeal.moderation_id:
            pending.append(appeal)
    return pending[:limit]
