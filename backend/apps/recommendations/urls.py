from django.urls import path

from . import views

urlpatterns = [
    path(
        "recommendations/basket/", views.BasketRecommendationView.as_view(), name="recommend-basket"
    ),
    path(
        "variants/<uuid:variant_id>/compare/",
        views.VariantComparisonView.as_view(),
        name="variant-compare",
    ),
]
