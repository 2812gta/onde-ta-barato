"""Contribution use cases: photo in, interpretation out, price only after confirmation."""

from dataclasses import asdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction

from apps.audit import services as audit
from apps.core import clock
from apps.prices import services as price_services
from apps.prices.evidence import sanitize_image
from apps.prices.models import EvidenceKind, PaymentCondition, PriceEvidence, PriceObservation
from apps.products.models import ProductVariant
from apps.stores.models import Store, StoreStatus
from apps.users.models import User

from . import fraud
from .extraction import Extraction, extract
from .matching import VariantSuggestion, suggest_variants
from .models import (
    DRAFT_TTL,
    ContributionStatus,
    FraudSignal,
    UserContribution,
)

MAX_OPEN_DRAFTS = 5
OUTLIER_LOOKBACK = timedelta(days=30)


def _extraction_payload(extraction: Extraction, suggestions: list[VariantSuggestion]) -> dict:
    return {
        "prices": [
            {**asdict(p), "value": str(p.value), "origin": p.origin.value}
            for p in extraction.prices
        ],
        "gtins": [{**asdict(g), "origin": g.origin.value} for g in extraction.gtins],
        "name_lines": extraction.name_lines,
        "variants": [
            {
                "variant_id": str(s.variant.pk),
                "basis": s.basis,
                "origin": s.origin.value,
                "score": round(s.score, 3),
            }
            for s in suggestions
        ],
    }


@transaction.atomic
def create_draft(
    *,
    user: User,
    store: Store,
    photo: bytes,
    ocr_text: str,
    captured_at: datetime | None = None,
) -> tuple[UserContribution, list[VariantSuggestion]]:
    """Keep the cleaned photo and what the device read. No price exists yet."""
    if store.status != StoreStatus.ACTIVE:
        raise ValidationError("Loja inativa.")
    _expire_stale(user)
    open_drafts = UserContribution.objects.filter(user=user, status=ContributionStatus.DRAFT)
    if open_drafts.count() >= MAX_OPEN_DRAFTS:
        raise ValidationError(
            "Você tem contribuições esperando confirmação. "
            "Confirme ou cancele antes de enviar outra."
        )
    now = clock.now()
    if captured_at is not None and captured_at > now + price_services.CLOCK_SKEW:
        raise ValidationError("A data da foto não pode estar no futuro.")
    clean, digest = sanitize_image(photo)
    extraction = extract(ocr_text)
    suggestions = suggest_variants(extraction)
    contribution = UserContribution(
        user=user,
        store=store,
        photo_sha256=digest,
        captured_at=captured_at,
        ocr_text=ocr_text,
        extraction=_extraction_payload(extraction, suggestions),
    )
    contribution.photo.save(f"{digest}.jpg", ContentFile(clean), save=False)
    contribution.save()
    return contribution, suggestions


def _discard_photo(contribution: UserContribution) -> None:
    if contribution.photo:
        contribution.photo.delete(save=False)
        contribution.photo = ""  # type: ignore[assignment]


def _cancel_draft(contribution: UserContribution) -> None:
    _discard_photo(contribution)
    contribution.status = ContributionStatus.CANCELLED
    contribution.resolved_at = clock.now()
    contribution.save(update_fields=["photo", "status", "resolved_at"])


def _expire_stale(user: User | None = None) -> int:
    """Delete photos of drafts nobody confirmed. Returns how many drafts expired."""
    queryset = UserContribution.objects.filter(
        status=ContributionStatus.DRAFT, created_at__lt=clock.now() - DRAFT_TTL
    )
    if user is not None:
        queryset = queryset.filter(user=user)
    count = 0
    for contribution in queryset:
        _cancel_draft(contribution)
        count += 1
    return count


def discard_open_drafts(user: User) -> int:
    """Cancel every open draft of a user and delete its photo (account deletion)."""
    count = 0
    for contribution in UserContribution.objects.filter(user=user, status=ContributionStatus.DRAFT):
        _cancel_draft(contribution)
        count += 1
    return count


def purge_stale_drafts() -> int:
    return _expire_stale()


def _own_draft(contribution_id: Any, user: User) -> UserContribution:
    contribution = (
        UserContribution.objects.select_for_update(of=("self",))
        .select_related("store__merchant")
        .filter(pk=contribution_id)
        .first()
    )
    if contribution is None or contribution.user_id != user.pk:
        raise PermissionDenied("Contribuição não encontrada.")
    if contribution.status != ContributionStatus.DRAFT:
        raise ValidationError("Esta contribuição já foi resolvida.")
    if contribution.created_at < clock.now() - DRAFT_TTL:
        raise ValidationError("Esta contribuição expirou. Fotografe o preço novamente.")
    return contribution


@transaction.atomic
def cancel(*, contribution_id: Any, user: User) -> UserContribution:
    contribution = _own_draft(contribution_id, user)
    _cancel_draft(contribution)
    return contribution


def _was_corrected(contribution: UserContribution, variant: ProductVariant, price: Decimal) -> bool:
    read_prices = {Decimal(p["value"]) for p in contribution.extraction.get("prices", [])}
    suggested = {v["variant_id"] for v in contribution.extraction.get("variants", [])}
    return price not in read_prices or str(variant.pk) not in suggested


def _fraud_context(
    contribution: UserContribution,
    *,
    variant: ProductVariant,
    price: Decimal,
    near_store: bool | None,
) -> fraud.FraudContext:
    now = clock.now()
    used_elsewhere = (
        UserContribution.objects.filter(
            photo_sha256=contribution.photo_sha256, status=ContributionStatus.CONFIRMED
        )
        .exclude(pk=contribution.pk)
        .values_list("user_id", flat=True)
    )
    evidence_users = PriceEvidence.objects.filter(sha256=contribution.photo_sha256).values_list(
        "created_by_id", flat=True
    )
    owners = set(used_elsewhere) | set(evidence_users)
    recent = list(
        PriceObservation.objects.filter(
            product_variant=variant, collected_at__gte=now - OUTLIER_LOOKBACK
        ).values_list("price", flat=True)[:200]
    )
    burst = UserContribution.objects.filter(
        user=contribution.user,
        status=ContributionStatus.CONFIRMED,
        resolved_at__gte=now - fraud.BURST_WINDOW,
    ).count()
    return fraud.FraudContext(
        price=price,
        now=now,
        captured_at=contribution.captured_at,
        recent_prices=recent,
        photo_used_by_other_user=any(uid != contribution.user_id for uid in owners),
        photo_used_by_same_user_elsewhere=contribution.user_id in owners,
        recent_contributions_by_user=burst,
        near_store=near_store,
    )


@transaction.atomic
def confirm(
    *,
    contribution_id: Any,
    user: User,
    variant: ProductVariant,
    price: Decimal,
    payment_condition: str = PaymentCondition.NORMAL,
    is_promotional: bool = False,
    lat: float | None = None,
    lon: float | None = None,
) -> tuple[UserContribution, price_services.RecordResult, list[FraudSignal]]:
    """The user's explicit CONFIRM (or CORRECT: values differ from what was read)."""
    contribution = _own_draft(contribution_id, user)
    if (lat is None) != (lon is None):
        raise ValidationError("Informe latitude e longitude juntas.")
    near = (
        None
        if lat is None or lon is None
        else price_services.is_near_store(contribution.store, lat, lon)
    )
    # Gathered before anything is written, so this contribution never counts against itself.
    fraud_context = _fraud_context(contribution, variant=variant, price=price, near_store=near)
    result = price_services.report_user_price(
        store=contribution.store,
        actor=user,
        variant=variant,
        price=price,
        payment_condition=payment_condition,
        is_promotional=is_promotional,
        collected_at=contribution.captured_at,
        user_lat=lat,
        user_lon=lon,
    )
    observation = result.observation
    clean = contribution.photo.read()
    contribution.photo.close()
    if observation.created_by_id == user.pk:
        price_services.attach_sanitized_evidence(
            observation=observation,
            actor=user,
            kind=EvidenceKind.PHOTO,
            clean=clean,
            digest=contribution.photo_sha256,
            captured_at=contribution.captured_at,
        )
    else:
        # The same price was already reported by someone else: this becomes an independent
        # confirmation of it. The photo is not kept (data minimization).
        price_services.confirm_price(observation=observation, actor=user, agrees=True)

    contribution.corrected = _was_corrected(contribution, variant, price)
    contribution.observation = observation
    contribution.status = ContributionStatus.CONFIRMED
    contribution.resolved_at = clock.now()
    signals = [
        FraudSignal.objects.create(
            contribution=contribution, kind=s.kind, severity=s.severity, detail=s.detail
        )
        for s in fraud.evaluate(fraud_context)
    ]
    _discard_photo(contribution)
    contribution.save()
    audit.record(
        "contribution.confirmed",
        actor=user,
        entity_type="user_contribution",
        entity_id=contribution.pk,
        new_value={
            "observation": str(observation.pk),
            "corrected": contribution.corrected,
            "signals": [s.kind for s in signals],
        },
    )
    return contribution, result, signals
