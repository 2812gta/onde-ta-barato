"""Shopping cart use cases. The cart belongs to its user; callers scope by `user`."""

from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.core import clock
from apps.products.models import ProductVariant
from apps.shopping_lists.models import ShoppingList
from apps.stores.models import Store, StoreStatus
from apps.users.models import User

from .models import CartItem, CartStatus, ShoppingCart
from .pricing import PricedCart, price_cart

MAX_ITEMS = 100
MAX_QUANTITY = Decimal("1000")
PAYMENTS = {"NORMAL", "PIX", "DEBIT", "CREDIT"}


def open_cart(user: User) -> ShoppingCart | None:
    return ShoppingCart.objects.filter(user=user, status=CartStatus.OPEN).first()


def get_or_open_cart(user: User) -> ShoppingCart:
    cart = open_cart(user)
    if cart is not None:
        return cart
    try:
        with transaction.atomic():
            return ShoppingCart.objects.create(user=user)
    except IntegrityError:  # two requests raced to open the first cart
        return ShoppingCart.objects.get(user=user, status=CartStatus.OPEN)


def configure(
    *,
    cart: ShoppingCart,
    changes: dict[str, Any],
) -> ShoppingCart:
    """Apply the store and shopper settings present in `changes` (absent keys stay as they are)."""
    if "store" in changes:
        store: Store | None = changes["store"]
        if store is not None and store.status != StoreStatus.ACTIVE:
            raise ValidationError("Loja inativa.")
        cart.store = store
    if "payment_condition" in changes:
        if changes["payment_condition"] not in PAYMENTS:
            raise ValidationError("Forma de pagamento inválida.")
        cart.payment_condition = changes["payment_condition"]
    if "has_loyalty" in changes:
        cart.has_loyalty = bool(changes["has_loyalty"])
    if "coupon_codes" in changes:
        cart.coupon_codes = sorted({str(c).strip().upper() for c in changes["coupon_codes"] if c})
    cart.save()
    return cart


def _check_quantity(quantity: Decimal) -> None:
    if not 0 < quantity <= MAX_QUANTITY:
        raise ValidationError("Quantidade fora do intervalo permitido.")


@transaction.atomic
def add_item(*, cart: ShoppingCart, variant: ProductVariant, quantity: Decimal) -> CartItem:
    """Adding a product already in the cart adds to its quantity."""
    _check_quantity(quantity)
    ShoppingCart.objects.select_for_update().get(pk=cart.pk)
    item = CartItem.objects.filter(cart=cart, product_variant=variant).first()
    if item is None:
        if cart.items.count() >= MAX_ITEMS:
            raise ValidationError(f"Limite de {MAX_ITEMS} itens no carrinho atingido.")
        return CartItem.objects.create(cart=cart, product_variant=variant, quantity=quantity)
    total = item.quantity + quantity
    _check_quantity(total)
    item.quantity = total
    item.save(update_fields=["quantity", "updated_at"])
    return item


def update_item(
    *, item: CartItem, quantity: Decimal | None = None, in_basket: bool | None = None
) -> CartItem:
    fields = ["updated_at"]
    if quantity is not None:
        _check_quantity(quantity)
        item.quantity = quantity
        fields.append("quantity")
    if in_basket is not None:
        item.in_basket = in_basket
        fields.append("in_basket")
    item.save(update_fields=fields)
    return item


@transaction.atomic
def import_list(*, cart: ShoppingCart, shopping_list: ShoppingList) -> int:
    """Copy a list into the cart (quantities add up). Returns how many products were copied."""
    copied = 0
    for list_item in shopping_list.items.select_related("product_variant"):
        add_item(cart=cart, variant=list_item.product_variant, quantity=list_item.quantity)
        copied += 1
    return copied


@transaction.atomic
def close_cart(*, cart: ShoppingCart) -> PricedCart:
    """Finish the shopping trip, keeping the final total and savings as they were priced."""
    if not cart.items.exists():
        raise ValidationError("O carrinho está vazio.")
    now = clock.now()
    priced = price_cart(cart, now)
    cart.status = CartStatus.CLOSED
    cart.closed_at = now
    cart.final_total = priced.total
    cart.final_savings = priced.savings
    cart.save(update_fields=["status", "closed_at", "final_total", "final_savings", "updated_at"])
    return priced
