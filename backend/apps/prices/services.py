"""Price write use cases. Every price keeps its source, author, time and predecessor."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.contrib.gis.measure import D
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction

from apps.audit import services as audit
from apps.core import clock
from apps.core.money import quantize_money
from apps.merchants import services as merchant_services
from apps.products.models import ProductVariant
from apps.stores.models import Store, StoreStatus
from apps.stores.selectors import point_from
from apps.users.models import User

from .confidence import ConfidenceInput, compute_confidence
from .evidence import sanitize_image
from .freshness import Freshness, freshness
from .models import (
    EvidenceKind,
    PaymentCondition,
    PriceConfirmation,
    PriceEvidence,
    PriceObservation,
    PriceSource,
)
from .selectors import ttl_hours_for

MAX_PRICE = Decimal("99999.99")
MAX_BACKDATE = timedelta(days=30)
CLOCK_SKEW = timedelta(minutes=5)
LOCATION_RADIUS_M = 500  # GPS indoors is poor; coordinates are checked, never stored


@dataclass(frozen=True)
class RecordResult:
    observation: PriceObservation
    created: bool


def _dedup_window() -> timedelta:
    return timedelta(hours=getattr(settings, "PRICE_DEDUP_HOURS", 6))


def _near_store(store: Store, lat: float, lon: float) -> bool:
    origin = point_from(lat, lon)
    return Store.objects.filter(
        pk=store.pk, location__dwithin=(origin, D(m=LOCATION_RADIUS_M))
    ).exists()


def is_near_store(store: Store, lat: float, lon: float) -> bool:
    """Whether a device position is close enough to vouch for a store visit."""
    return _near_store(store, lat, lon)


@transaction.atomic
def record_price(
    *,
    variant: ProductVariant,
    store: Store,
    price: Decimal | str,
    source: str,
    created_by: User | None,
    payment_condition: str = PaymentCondition.NORMAL,
    is_promotional: bool = False,
    collected_at: datetime | None = None,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
    user_lat: float | None = None,
    user_lon: float | None = None,
) -> RecordResult:
    """Append an observation. Authorization is the caller's job (see the wrappers below)."""
    if store.status != StoreStatus.ACTIVE:
        raise ValidationError("Loja inativa.")
    amount = quantize_money(price)
    if not 0 < amount <= MAX_PRICE:
        raise ValidationError("Preço fora do intervalo permitido.")
    now = clock.now()
    collected_at = collected_at or now
    if collected_at > now + CLOCK_SKEW:
        raise ValidationError("A data da coleta não pode estar no futuro.")
    if collected_at < now - MAX_BACKDATE:
        raise ValidationError("A data da coleta é antiga demais para ser registrada.")
    if valid_until is not None and valid_until <= collected_at:
        raise ValidationError("A validade deve ser posterior à coleta.")
    if (user_lat is None) != (user_lon is None):
        raise ValidationError("Informe latitude e longitude juntas.")

    previous = (
        PriceObservation.objects.filter(
            product_variant=variant, store=store, payment_condition=payment_condition, source=source
        )
        .order_by("-collected_at", "-created_at")
        .first()
    )
    if (
        previous is not None
        and previous.price == amount
        and previous.is_promotional == is_promotional
        and previous.valid_until == valid_until
        and collected_at - previous.collected_at < _dedup_window()
        and previous.collected_at <= collected_at
    ):
        return RecordResult(previous, created=False)  # same price re-reported: no new row

    location_ok = (
        user_lat is not None and user_lon is not None and _near_store(store, user_lat, user_lon)
    )
    merchant = store.merchant
    confidence = compute_confidence(
        ConfidenceInput(
            source=source,
            age_hours=0,
            ttl_hours=ttl_hours_for(variant),
            merchant_verified=bool(
                source == PriceSource.MERCHANT and merchant is not None and merchant.is_verified
            ),
            location_verified=location_ok,
        )
    )
    observation = PriceObservation.objects.create(
        product_variant=variant,
        store=store,
        price=amount,
        payment_condition=payment_condition,
        is_promotional=is_promotional,
        source=source,
        collected_at=collected_at,
        valid_from=valid_from,
        valid_until=valid_until,
        confidence_score=confidence.score,
        confidence_level=confidence.level,
        created_by=created_by,
        supersedes=previous,
        location_verified=location_ok,
    )
    audit.record(
        "price.recorded",
        actor=created_by,
        entity_type="price_observation",
        entity_id=observation.pk,
        previous_value={"price": str(previous.price)} if previous else None,
        new_value={
            "price": str(amount),
            "source": source,
            "store": str(store.pk),
            "variant": str(variant.pk),
            "payment_condition": payment_condition,
        },
    )
    return RecordResult(observation, created=True)


def publish_merchant_price(*, store: Store, actor: User, **kwargs: Any) -> RecordResult:
    """A member of the store's merchant publishes the store's own price."""
    if store.merchant is None or not merchant_services.can_publish(actor, store.merchant):
        raise PermissionDenied("Você não pode publicar preços desta loja.")
    kwargs.pop("user_lat", None)
    kwargs.pop("user_lon", None)
    return record_price(store=store, created_by=actor, source=PriceSource.MERCHANT, **kwargs)


def report_user_price(*, store: Store, actor: User, **kwargs: Any) -> RecordResult:
    """A consumer reports a price they saw. Store staff cannot pose as independent consumers."""
    if store.merchant is not None and merchant_services.membership_role(actor, store.merchant):
        raise ValidationError(
            "Equipe da loja deve publicar como estabelecimento, não como cliente."
        )
    return record_price(store=store, created_by=actor, source=PriceSource.USER, **kwargs)


@transaction.atomic
def confirm_price(*, observation: PriceObservation, actor: User, agrees: bool) -> PriceConfirmation:
    """Independent confirmation or dispute. Authors and store staff cannot vote."""
    if observation.created_by_id == actor.pk:
        raise ValidationError("Você não pode confirmar o próprio registro.")
    merchant = observation.store.merchant
    if merchant is not None and merchant_services.membership_role(actor, merchant):
        raise ValidationError("Equipe da loja não pode confirmar preços da própria loja.")
    state = freshness(
        collected_at=observation.collected_at,
        valid_until=observation.valid_until,
        ttl_hours=ttl_hours_for(observation.product_variant),
        now=clock.now(),
    )
    if state == Freshness.EXPIRED:
        raise ValidationError("Este preço expirou e não pode mais ser confirmado.")
    try:
        with transaction.atomic():
            confirmation = PriceConfirmation.objects.create(
                observation=observation, user=actor, agrees=agrees
            )
    except IntegrityError as exc:
        raise ValidationError("Você já avaliou este preço.") from exc
    audit.record(
        "price.confirmation",
        actor=actor,
        entity_type="price_observation",
        entity_id=observation.pk,
        new_value={"agrees": agrees},
    )
    return confirmation


@transaction.atomic
def add_evidence(
    *,
    observation: PriceObservation,
    actor: User,
    kind: str,
    content: bytes | None = None,
    source_url: str = "",
    captured_at: datetime | None = None,
) -> PriceEvidence:
    if observation.created_by_id != actor.pk:
        raise PermissionDenied("Apenas o autor do registro anexa evidência.")
    if kind == EvidenceKind.URL:
        if not source_url.startswith(("https://", "http://")):
            raise ValidationError("Link inválido.")
        return PriceEvidence.objects.create(
            observation=observation, kind=kind, source_url=source_url, created_by=actor
        )
    if content is None:
        raise ValidationError("Arquivo obrigatório.")
    clean, digest = sanitize_image(content)
    return attach_sanitized_evidence(
        observation=observation,
        actor=actor,
        kind=kind,
        clean=clean,
        digest=digest,
        captured_at=captured_at,
    )


@transaction.atomic
def attach_sanitized_evidence(
    *,
    observation: PriceObservation,
    actor: User,
    kind: str,
    clean: bytes,
    digest: str,
    captured_at: datetime | None = None,
) -> PriceEvidence:
    """Store an image that `sanitize_image` already cleaned (no second re-encode)."""
    if observation.created_by_id != actor.pk:
        raise PermissionDenied("Apenas o autor do registro anexa evidência.")
    evidence = PriceEvidence(
        observation=observation,
        kind=kind,
        sha256=digest,
        captured_at=captured_at,
        created_by=actor,
    )
    evidence.file.save(f"{digest}.jpg", ContentFile(clean), save=False)
    evidence.save()
    audit.record(
        "price.evidence_added",
        actor=actor,
        entity_type="price_observation",
        entity_id=observation.pk,
        new_value={"kind": kind, "sha256": digest},
    )
    return evidence
