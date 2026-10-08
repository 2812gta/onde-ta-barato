from django.urls import path

from . import views

urlpatterns = [
    path(
        "variants/<uuid:variant_id>/prices/search/",
        views.VariantPricesSearchView.as_view(),
        name="variant-prices-search",
    ),
    path(
        "variants/<uuid:variant_id>/price-history/",
        views.PriceHistoryView.as_view(),
        name="variant-price-history",
    ),
    path("stores/<uuid:store_id>/prices/", views.MerchantPriceView.as_view(), name="store-prices"),
    path(
        "stores/<uuid:store_id>/prices/report/",
        views.UserPriceReportView.as_view(),
        name="store-price-report",
    ),
    path(
        "prices/<uuid:price_id>/confirmations/",
        views.ConfirmationView.as_view(),
        name="price-confirmation",
    ),
]
