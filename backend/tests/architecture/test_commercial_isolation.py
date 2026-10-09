"""Architecture guard: payment must never reach price ranking, confidence or verification.

The rule is enforced structurally (imports and field names), not by trusting reviewers.
Modules that decide what a consumer sees as price, trust or order may not depend on
anything commercial. When the commercial apps exist (subscriptions, ads, campaigns) these
tests are what stop a future change from wiring them in.
"""

import ast
from pathlib import Path

import pytest

APPS = Path(__file__).resolve().parents[2] / "apps"

# Read-side / decision modules: what the consumer sees as price, trust and order.
PROTECTED = [
    "prices/confidence.py",
    "prices/freshness.py",
    "prices/selectors.py",
    "prices/models.py",
    "products/units.py",
    "products/normalization.py",
    "stores/selectors.py",
    "promotions/engine.py",
    "promotions/selectors.py",
    "recommendations/config.py",
    "recommendations/types.py",
    "recommendations/quotes.py",
    "recommendations/engine.py",
    "recommendations/explain.py",
    "recommendations/selectors.py",
    "recommendations/services.py",
    "recommendations/present.py",
    "shopping_cart/pricing.py",
    "contributions/extraction.py",
    "contributions/fraud.py",
    "contributions/matching.py",
    "moderation/selectors.py",
    "moderation/services.py",
]
# Apps that carry money from merchants to the platform (some are created in later milestones).
COMMERCIAL_APPS = {
    "subscriptions",
    "advertising",
    "ads",
    "campaigns",
    "sponsorship",
    "billing",
    "payments",
}
COMMERCIAL_WORDS = (
    "subscription",
    "sponsor",
    "advertis",
    "campaign",
    "commercial_score",
    "ad_budget",
    "advertising_budget",
    "paid_plan",
    "premium",
)


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


@pytest.mark.parametrize("relative", PROTECTED)
def test_protected_module_has_no_commercial_imports(relative):
    path = APPS / relative
    assert path.exists(), f"update PROTECTED: {relative} moved"
    for module in imported_modules(path):
        parts = set(module.split("."))
        assert not parts & COMMERCIAL_APPS, f"{relative} imports {module}"


@pytest.mark.parametrize("relative", PROTECTED)
def test_protected_module_has_no_commercial_identifiers(relative):
    tree = ast.parse((APPS / relative).read_text(encoding="utf-8"))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    names |= {n.arg for n in ast.walk(tree) if isinstance(n, ast.arg)}
    for name in names:
        assert not any(word in name.lower() for word in COMMERCIAL_WORDS), f"{relative}: {name}"


def test_price_models_have_no_commercial_fields():
    from apps.prices.models import PriceObservation

    for field in PriceObservation._meta.get_fields():
        assert not any(word in field.name.lower() for word in COMMERCIAL_WORDS), field.name


def test_merchant_verification_is_not_purchasable():
    """VERIFIED only comes from the review workflow, never from a plan or payment field."""
    from apps.merchants.models import Merchant

    for field in Merchant._meta.get_fields():
        assert not any(word in field.name.lower() for word in COMMERCIAL_WORDS), field.name


def test_commercial_apps_cannot_be_installed_without_this_test_being_revisited(settings):
    """If a commercial app is added, a human must extend PROTECTED/these tests consciously."""
    installed = {entry.split(".")[-1] for entry in settings.INSTALLED_APPS}
    assert not installed & COMMERCIAL_APPS, (
        "A commercial app was installed. Review tests/architecture/test_commercial_isolation.py "
        "and prove it cannot influence price, confidence, verification or ordering."
    )
