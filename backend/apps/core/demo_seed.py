"""Demo data for local development and demos. FICTIONAL: never run against production.

Everything goes through the same services the API uses (merchant verification, price
recording, promotions, confirmations), so demo rows obey the same rules and are audited.
The set is built to exercise the M3 scenarios: unit price across sizes, a verified vs an
unverified merchant, stale prices, a disputed price, and each kind of promotion.

Idempotent: every step looks for what it would create and skips it. Price history is
append-only, so there is no "reset"; to start over, recreate the development database.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError

from apps.core import clock
from apps.merchants import services as merchant_services
from apps.merchants.models import Merchant, VerificationStatus
from apps.prices import services as price_services
from apps.prices.models import PriceObservation, PriceSource
from apps.products.models import Category, ProductVariant, Unit
from apps.products.services import get_or_create_variant
from apps.promotions import services as promotion_services
from apps.promotions.models import Promotion
from apps.stores.models import Store, StoreSource, StoreType
from apps.stores.selectors import point_from
from apps.users.models import Role, User

DEMO_EMAIL_DOMAIN = "demo.ondetabarato.invalid"  # reserved TLD: can never receive mail
DEMO_PREFIX = "[DEMO] "
DEMO_SOURCE_REF = "demo"


def demo_email(handle: str) -> str:
    return f"{handle}@{DEMO_EMAIL_DOMAIN}"


@dataclass(frozen=True)
class DemoProduct:
    key: str
    name: str
    brand: str
    category: str  # Category slug
    label: str
    quantity: str
    unit: str
    base_price: str


CATALOG = [
    DemoProduct(
        "arroz-1kg",
        "Arroz Branco",
        "Grão Dourado",
        "mercearia",
        "Tipo 1",
        "1",
        Unit.KILOGRAM,
        "5.99",
    ),
    DemoProduct(
        "arroz-5kg",
        "Arroz Branco",
        "Grão Dourado",
        "mercearia",
        "Tipo 1",
        "5",
        Unit.KILOGRAM,
        "27.90",
    ),
    DemoProduct(
        "feijao-1kg", "Feijão Carioca", "Campo Verde", "mercearia", "", "1", Unit.KILOGRAM, "7.49"
    ),
    DemoProduct(
        "leite-1l", "Leite Integral", "Vale Branco", "laticinios", "", "1", Unit.LITER, "4.79"
    ),
    DemoProduct(
        "oleo-900ml", "Óleo de Soja", "Sol Dourado", "mercearia", "", "900", Unit.MILLILITER, "7.99"
    ),
    DemoProduct(
        "cafe-500g",
        "Café Torrado e Moído",
        "Serra Alta",
        "mercearia",
        "",
        "500",
        Unit.GRAM,
        "18.90",
    ),
    DemoProduct(
        "cafe-250g",
        "Café Torrado e Moído",
        "Serra Alta",
        "mercearia",
        "",
        "250",
        Unit.GRAM,
        "10.50",
    ),
    DemoProduct(
        "acucar-1kg", "Açúcar Refinado", "Doce Vida", "mercearia", "", "1", Unit.KILOGRAM, "4.59"
    ),
    DemoProduct(
        "macarrao-500g",
        "Macarrão Espaguete",
        "Massa Boa",
        "mercearia",
        "",
        "500",
        Unit.GRAM,
        "3.89",
    ),
    DemoProduct(
        "refri-2l", "Refrigerante Cola", "Bolha Mágica", "bebidas", "", "2", Unit.LITER, "9.49"
    ),
    DemoProduct(
        "refri-350ml",
        "Refrigerante Cola",
        "Bolha Mágica",
        "bebidas",
        "Lata",
        "350",
        Unit.MILLILITER,
        "3.79",
    ),
    DemoProduct(
        "sabao-1kg", "Sabão em Pó", "Brilho Claro", "limpeza", "", "1", Unit.KILOGRAM, "14.90"
    ),
    DemoProduct(
        "papel-12",
        "Papel Higiênico",
        "Suave Pura",
        "higiene-pessoal",
        "12 rolos",
        "12",
        Unit.UNIT,
        "16.90",
    ),
    DemoProduct("banana-kg", "Banana Prata", "", "hortifruti", "", "1", Unit.KILOGRAM, "6.99"),
    DemoProduct("tomate-kg", "Tomate", "", "hortifruti", "", "1", Unit.KILOGRAM, "8.49"),
    DemoProduct("pao-kg", "Pão Francês", "", "padaria", "", "1", Unit.KILOGRAM, "16.00"),
]
BASE_PRICES = {p.key: Decimal(p.base_price) for p in CATALOG}
FRESH = ["banana-kg", "tomate-kg"]
PACKAGED = [p.key for p in CATALOG if p.key not in {*FRESH, "pao-kg"}]


@dataclass(frozen=True)
class DemoStore:
    key: str
    name: str
    store_type: str
    lat: float
    lon: float
    neighborhood: str
    merchant: str | None  # key into MERCHANTS; None = unclaimed store (user reports only)


# Approximate neighborhood centers in Fortaleza/CE; the businesses are fictional.
STORES = [
    DemoStore(
        "aldeota",
        "Supermercado Aldeota",
        StoreType.SUPERMARKET,
        -3.7385,
        -38.4965,
        "Aldeota",
        "alfa",
    ),
    DemoStore(
        "messejana",
        "Supermercado Messejana",
        StoreType.SUPERMARKET,
        -3.8366,
        -38.4938,
        "Messejana",
        "alfa",
    ),
    DemoStore(
        "parangaba",
        "Atacado Parangaba",
        StoreType.WHOLESALE,
        -3.7766,
        -38.5575,
        "Parangaba",
        "beta",
    ),
    DemoStore(
        "benfica", "Mercadinho Benfica", StoreType.MINIMARKET, -3.7400, -38.5390, "Benfica", "gama"
    ),
    DemoStore(
        "meireles", "Padaria Meireles", StoreType.BAKERY, -3.7270, -38.4950, "Meireles", None
    ),
    DemoStore(
        "centro", "Hortifruti Centro", StoreType.GREENGROCER, -3.7275, -38.5270, "Centro", None
    ),
]

# key -> (trade name, final status). "gama" stays PENDING: its prices must count for less.
MERCHANTS = {
    "alfa": ("Rede Alfa", VerificationStatus.VERIFIED),
    "beta": ("Atacado Beta", VerificationStatus.VERIFIED),
    "gama": ("Mercadinho Gama", VerificationStatus.PENDING),
}

# Price factor per store relative to the catalog base price.
FACTORS = {
    "aldeota": Decimal("1.00"),
    "messejana": Decimal("0.97"),
    "parangaba": Decimal("0.90"),
    "benfica": Decimal("1.08"),
}
# The wholesaler is only cheaper on the big presentations; small ones cost more per unit.
WHOLESALE_BIG = {"arroz-5kg", "papel-12", "refri-2l", "cafe-500g"}


@dataclass
class SeedReport:
    created: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)
    new_users: list[str] = field(default_factory=list)

    def made(self, what: str) -> None:
        self.created[what] = self.created.get(what, 0) + 1

    def existed(self, what: str) -> None:
        self.skipped[what] = self.skipped.get(what, 0) + 1


def _user(report: SeedReport, handle: str, role: str, name: str, password: str) -> User:
    email = demo_email(handle)
    user = User.objects.filter(email=email).first()
    if user is not None:
        report.existed("users")
        return user
    user = User.objects.create_user(
        email=email,
        password=password,
        role=role,
        display_name=f"{DEMO_PREFIX}{name}",
        email_verified_at=clock.now(),
    )
    report.made("users")
    report.new_users.append(email)
    return user


def _merchant(report: SeedReport, key: str, owner: User, moderator: User) -> Merchant:
    trade_name, final_status = MERCHANTS[key]
    merchant = Merchant.objects.filter(trade_name=f"{DEMO_PREFIX}{trade_name}").first()
    if merchant is None:
        merchant = merchant_services.create_merchant(
            owner=owner,
            legal_name=f"{DEMO_PREFIX}{trade_name} Ltda",
            trade_name=f"{DEMO_PREFIX}{trade_name}",
            contact_email=demo_email(f"contato-{key}"),
        )
        report.made("merchants")
    else:
        report.existed("merchants")
    if (
        final_status == VerificationStatus.VERIFIED
        and merchant.status == VerificationStatus.PENDING
    ):
        merchant_services.transition(
            merchant=merchant, to_status=VerificationStatus.UNDER_REVIEW, actor=owner
        )
        merchant_services.transition(
            merchant=merchant,
            to_status=VerificationStatus.VERIFIED,
            actor=moderator,
            notes="Dados de demonstração.",
        )
    return merchant


def _store(report: SeedReport, spec: DemoStore, merchant: Merchant | None) -> Store:
    store = Store.all_objects.filter(
        source=StoreSource.MERCHANT, external_id=f"demo-{spec.key}"
    ).first()
    if store is not None:
        report.existed("stores")
        return store
    store = Store.objects.create(
        merchant=merchant,
        name=f"{DEMO_PREFIX}{spec.name}",
        store_type=spec.store_type,
        neighborhood=spec.neighborhood,
        city="Fortaleza",
        state="CE",
        location=point_from(spec.lat, spec.lon),
        source=StoreSource.MERCHANT,
        external_id=f"demo-{spec.key}",
    )
    report.made("stores")
    return store


def _variants(report: SeedReport) -> dict[str, ProductVariant]:
    out: dict[str, ProductVariant] = {}
    for item in CATALOG:
        variant, created = get_or_create_variant(
            name=item.name,
            brand_name=item.brand,
            category=Category.objects.filter(slug=item.category).first(),
            label=item.label,
            quantity=Decimal(item.quantity),
            unit=item.unit,
            source_ref=DEMO_SOURCE_REF,
        )
        out[item.key] = variant
        if created:
            report.made("variants")
        else:
            report.existed("variants")
    return out


def _price(store_key: str, variant_key: str, position: int) -> Decimal:
    factor = FACTORS[store_key]
    if store_key == "parangaba" and variant_key not in WHOLESALE_BIG:
        factor = Decimal("1.04")
    jitter = Decimal((position * 7) % 5 - 2) / Decimal(100)  # deterministic, -2%..+2%
    return (BASE_PRICES[variant_key] * (factor + jitter)).quantize(Decimal("0.01"))


def _has_price(store: Store, variant: ProductVariant, source: str, promo: bool = False) -> bool:
    return PriceObservation.objects.filter(
        store=store, product_variant=variant, source=source, is_promotional=promo
    ).exists()


def _merchant_prices(
    report: SeedReport,
    stores: dict[str, Store],
    variants: dict[str, ProductVariant],
    owners: dict[str, User],
) -> None:
    now = clock.now()
    for spec in STORES:
        if spec.merchant is None:
            continue
        store, owner = stores[spec.key], owners[spec.merchant]
        keys = PACKAGED if spec.key == "parangaba" else PACKAGED + FRESH
        for position, key in enumerate(keys):
            variant = variants[key]
            if _has_price(store, variant, PriceSource.MERCHANT):
                report.existed("prices")
                continue
            # Messejana's fresh produce is 10 days old: stale, so it must be discounted.
            stale = spec.key == "messejana" and key in FRESH
            age = timedelta(days=10) if stale else timedelta(hours=2 + position)
            price_services.publish_merchant_price(
                store=store,
                actor=owner,
                variant=variant,
                price=_price(spec.key, key, position),
                collected_at=now - age,
            )
            report.made("prices")
    promo_variant = variants["cafe-500g"]
    if _has_price(stores["aldeota"], promo_variant, PriceSource.MERCHANT, promo=True):
        report.existed("prices")
    else:
        price_services.publish_merchant_price(
            store=stores["aldeota"],
            actor=owners["alfa"],
            variant=promo_variant,
            price="15.90",
            is_promotional=True,
            collected_at=now - timedelta(hours=1),
            valid_until=now + timedelta(days=3),
        )
        report.made("prices")


def _user_prices(
    report: SeedReport,
    stores: dict[str, Store],
    variants: dict[str, ProductVariant],
    customers: list[User],
) -> list[PriceObservation]:
    now = clock.now()
    reports = [  # (store, variant, price, customer index, hours ago)
        ("meireles", "pao-kg", "15.50", 0, 3),
        ("meireles", "cafe-250g", "10.20", 1, 5),
        ("centro", "banana-kg", "5.99", 1, 4),
        ("centro", "tomate-kg", "7.49", 2, 6),
        # Disputed: far below the merchant's own price for the same item.
        ("aldeota", "arroz-5kg", "20.90", 2, 8),
    ]
    found: list[PriceObservation] = []
    for store_key, variant_key, price, who, hours in reports:
        store, variant = stores[store_key], variants[variant_key]
        existing = PriceObservation.objects.filter(
            store=store, product_variant=variant, source=PriceSource.USER
        ).first()
        if existing is not None:
            report.existed("prices")
            found.append(existing)
            continue
        result = price_services.report_user_price(
            store=store,
            actor=customers[who],
            variant=variant,
            price=price,
            collected_at=now - timedelta(hours=hours),
        )
        report.made("prices")
        found.append(result.observation)
    return found


def _confirmations(
    report: SeedReport, observations: list[PriceObservation], customers: list[User]
) -> None:
    votes = [  # (observation index, customer index, agrees)
        (0, 1, True),
        (0, 2, True),
        (2, 0, True),
        (4, 0, False),  # the cheap rice at Aldeota is disputed by two people
        (4, 1, False),
    ]
    for obs_index, who, agrees in votes:
        try:
            price_services.confirm_price(
                observation=observations[obs_index], actor=customers[who], agrees=agrees
            )
            report.made("confirmations")
        except ValidationError:
            report.existed("confirmations")  # already voted (re-run)


def _promotions(
    report: SeedReport,
    stores: dict[str, Store],
    variants: dict[str, ProductVariant],
    owners: dict[str, User],
) -> None:
    now = clock.now()
    plan: list[tuple[str, str, str, str, dict[str, Any]]] = [
        (
            "aldeota",
            "alfa",
            "macarrao-500g",
            "3 por R$ 10",
            {"type": "FIXED_PRICE", "bundle_quantity": 3, "bundle_price": "10.00"},
        ),
        (
            "aldeota",
            "alfa",
            "feijao-1kg",
            "Leve 3, pague 2",
            {"type": "BUY_X_PAY_Y", "buy": 3, "pay": 2},
        ),
        (
            "messejana",
            "alfa",
            "leite-1l",
            "Terça: 10% de desconto",
            {
                "type": "DAY_LIMITED",
                "weekdays": [1],
                "base": {"type": "PERCENTAGE", "percent": "10"},
            },
        ),
        (
            "parangaba",
            "beta",
            "refri-2l",
            "Pix: 5% de desconto",
            {"type": "PIX_PRICE", "percent": "5"},
        ),
        # Unverified merchant: shown, but never as a confirmed promotion.
        (
            "benfica",
            "gama",
            "sabao-1kg",
            "2º sabão com 30% off",
            {"type": "SECOND_UNIT_DISCOUNT", "percent": "30"},
        ),
    ]
    for store_key, owner_key, variant_key, title, rule in plan:
        store, variant = stores[store_key], variants[variant_key]
        if Promotion.objects.filter(store=store, product_variant=variant, title=title).exists():
            report.existed("promotions")
            continue
        promotion_services.create_promotion(
            store=store,
            actor=owners[owner_key],
            variant=variant,
            title=title,
            rule=rule,
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=7),
        )
        report.made("promotions")


def seed(password: str) -> SeedReport:
    report = SeedReport()
    moderator = _user(report, "moderador", Role.MODERATOR, "Moderador", password)
    owners = {
        key: _user(report, f"dono-{key}", Role.CUSTOMER, f"Dono {name}", password)
        for key, (name, _) in MERCHANTS.items()
    }
    customers = [
        _user(report, f"cliente{i}", Role.CUSTOMER, f"Cliente {i}", password) for i in (1, 2, 3)
    ]
    merchants = {key: _merchant(report, key, owners[key], moderator) for key in MERCHANTS}
    stores = {
        spec.key: _store(report, spec, merchants[spec.merchant] if spec.merchant else None)
        for spec in STORES
    }
    variants = _variants(report)
    _merchant_prices(report, stores, variants, owners)
    observations = _user_prices(report, stores, variants, customers)
    _confirmations(report, observations, customers)
    _promotions(report, stores, variants, owners)
    return report
