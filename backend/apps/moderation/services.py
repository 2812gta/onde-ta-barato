"""Moderation use cases. Every decision needs a reason and leaves an audit entry."""

from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.audit import services as audit
from apps.contributions.models import FraudSignal
from apps.prices.models import PriceObservation, PriceSource
from apps.users.models import User

from . import selectors
from .models import ModerationAction, PriceAppeal, PriceModeration, SignalDecision, SignalReview

MIN_TEXT = 10
MAX_TEXT = 1000


def _text(value: str, what: str) -> str:
    value = (value or "").strip()
    if len(value) < MIN_TEXT:
        raise ValidationError(f"{what} precisa ter pelo menos {MIN_TEXT} caracteres.")
    if len(value) > MAX_TEXT:
        raise ValidationError(f"{what} pode ter no máximo {MAX_TEXT} caracteres.")
    return value


def _lock(observation_id: Any) -> PriceObservation:
    """Serialize decisions on one price so two moderators cannot both 'hide' it."""
    return PriceObservation.objects.select_for_update().get(pk=observation_id)


def _decide(
    observation: PriceObservation, actor: User, action: str, reason: str
) -> PriceModeration:
    decision = PriceModeration.objects.create(
        observation=observation, action=action, reason=reason, actor=actor
    )
    audit.record(
        f"moderation.price_{action.lower()}",
        actor=actor,
        entity_type="price_observation",
        entity_id=observation.pk,
        new_value={"reason": reason},
    )
    return decision


@transaction.atomic
def hide_price(*, observation: PriceObservation, actor: User, reason: str) -> PriceModeration:
    """Take a consumer price out of what others see. It stays in the records."""
    reason = _text(reason, "A justificativa")
    observation = _lock(observation.pk)
    if observation.source != PriceSource.USER:
        raise ValidationError("Apenas preços informados por consumidores são moderados aqui.")
    if observation.created_by_id == actor.pk:
        raise PermissionDenied("Você não pode moderar um preço que você mesmo informou.")
    if selectors.state_of(observation.pk).hidden:
        raise ValidationError("Este preço já está oculto.")
    return _decide(observation, actor, ModerationAction.HIDE, reason)


@transaction.atomic
def restore_price(*, observation: PriceObservation, actor: User, reason: str) -> PriceModeration:
    reason = _text(reason, "A justificativa")
    observation = _lock(observation.pk)
    if observation.created_by_id == actor.pk:
        raise PermissionDenied("Você não pode moderar um preço que você mesmo informou.")
    if not selectors.state_of(observation.pk).hidden:
        raise ValidationError("Este preço não está oculto.")
    return _decide(observation, actor, ModerationAction.RESTORE, reason)


@transaction.atomic
def uphold_hide(*, observation: PriceObservation, actor: User, reason: str) -> PriceModeration:
    """Answer an appeal by keeping the price hidden. The answer is final."""
    reason = _text(reason, "A justificativa")
    observation = _lock(observation.pk)
    if observation.created_by_id == actor.pk:
        raise PermissionDenied("Você não pode moderar um preço que você mesmo informou.")
    if selectors.state_of(observation.pk).state != selectors.APPEAL_PENDING:
        raise ValidationError("Não há recurso pendente para este preço.")
    return _decide(observation, actor, ModerationAction.UPHOLD, reason)


@transaction.atomic
def appeal(*, observation: PriceObservation, user: User, message: str) -> PriceAppeal:
    """The contributor contests the hiding of their own price. One appeal per decision."""
    message = _text(message, "A mensagem do recurso")
    observation = _lock(observation.pk)
    if observation.created_by_id != user.pk:
        raise PermissionDenied("Apenas quem informou o preço pode recorrer.")
    state = selectors.state_of(observation.pk)
    if state.state == selectors.UPHELD:
        raise ValidationError("O recurso deste preço já foi analisado.")
    if not state.can_appeal:
        raise ValidationError("Este preço não está oculto, ou já tem um recurso em análise.")
    created = PriceAppeal.objects.create(
        moderation=PriceModeration.objects.get(pk=state.hide_id), user=user, message=message
    )
    audit.record(
        "moderation.appeal",
        actor=user,
        entity_type="price_observation",
        entity_id=observation.pk,
        new_value={"message_length": len(message)},
    )
    return created


@transaction.atomic
def review_signal(
    *, signal: FraudSignal, actor: User, decision: str, note: str = ""
) -> SignalReview:
    """Record that a moderator looked at a signal. This hides nothing by itself."""
    if decision not in SignalDecision.values:
        raise ValidationError("Decisão inválida.")
    if signal.contribution.user_id == actor.pk:
        raise PermissionDenied("Você não pode revisar sinais das suas próprias contribuições.")
    note = (note or "").strip()[:MAX_TEXT]
    if SignalReview.objects.filter(signal=signal).exists():
        raise ValidationError("Este sinal já foi revisado.")
    review = SignalReview.objects.create(signal=signal, decision=decision, note=note, actor=actor)
    audit.record(
        "moderation.signal_reviewed",
        actor=actor,
        entity_type="fraud_signal",
        entity_id=signal.pk,
        new_value={"decision": decision, "kind": signal.kind},
    )
    return review
