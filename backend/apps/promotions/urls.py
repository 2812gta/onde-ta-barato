from django.urls import path

from . import views

urlpatterns = [
    path(
        "stores/<uuid:store_id>/promotions/",
        views.StorePromotionsView.as_view(),
        name="store-promotions",
    ),
    path("promotions/<uuid:promotion_id>/", views.PromotionDetailView.as_view(), name="promotion"),
    path("promotions/calculate/", views.CalculateView.as_view(), name="promotion-calculate"),
]
