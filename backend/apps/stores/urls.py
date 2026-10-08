from django.urls import path

from . import views

urlpatterns = [
    path("stores/search/", views.StoreSearchView.as_view(), name="store-search"),
    path("stores/<uuid:store_id>/", views.StoreDetailView.as_view(), name="store"),
    path(
        "merchants/<uuid:merchant_id>/stores/",
        views.MerchantStoresView.as_view(),
        name="merchant-stores",
    ),
]
