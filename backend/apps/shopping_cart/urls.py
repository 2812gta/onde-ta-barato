from django.urls import path

from . import views

urlpatterns = [
    path("shopping-cart/", views.CartView.as_view(), name="shopping-cart"),
    path("shopping-cart/items/", views.CartItemsView.as_view(), name="shopping-cart-items"),
    path(
        "shopping-cart/items/<uuid:item_id>/",
        views.CartItemDetailView.as_view(),
        name="shopping-cart-item",
    ),
    path(
        "shopping-cart/import-list/",
        views.CartImportListView.as_view(),
        name="shopping-cart-import-list",
    ),
    path("shopping-cart/close/", views.CartCloseView.as_view(), name="shopping-cart-close"),
]
