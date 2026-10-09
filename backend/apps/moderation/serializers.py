from rest_framework import serializers

from apps.contributions.models import FraudSignal

from . import selectors
from .models import PriceAppeal, SignalDecision


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=2000)


class AppealCreateSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=2000)


class SignalReviewSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=SignalDecision.choices)
    note = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


def _price_summary(observation) -> dict:  # type: ignore[no-untyped-def]
    return {
        "observation_id": str(observation.pk),
        "store": {"id": str(observation.store_id), "name": observation.store.name},
        "product": str(observation.product_variant),
        "price": str(observation.price),
        "source": observation.source,
        "collected_at": observation.collected_at,
        # The contributor is identified by an opaque id only; never an e-mail or a name.
        "contributor_id": str(observation.created_by_id) if observation.created_by_id else None,
        "moderation": selectors.state_of(observation.pk).state,
    }


def signal_row(signal: FraudSignal) -> dict:
    contribution = signal.contribution
    row = {
        "id": str(signal.pk),
        "kind": signal.kind,
        "severity": signal.severity,
        "detail": signal.detail,
        "created_at": signal.created_at,
        "contribution_id": str(contribution.pk),
        "corrected": contribution.corrected,
    }
    if contribution.observation is not None:
        row["price"] = _price_summary(contribution.observation)
    return row


def appeal_row(appeal: PriceAppeal) -> dict:
    return {
        "id": str(appeal.pk),
        "message": appeal.message,
        "created_at": appeal.created_at,
        "hidden_because": appeal.moderation.reason,
        "price": _price_summary(appeal.moderation.observation),
    }
