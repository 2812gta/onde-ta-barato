from django.urls import path

from . import views

urlpatterns = [
    path("moderation/queue/", views.QueueView.as_view(), name="moderation-queue"),
    path(
        "moderation/signals/<uuid:signal_id>/review/",
        views.SignalReviewView.as_view(),
        name="moderation-signal-review",
    ),
    path(
        "moderation/prices/<uuid:observation_id>/hide/",
        views.HidePriceView.as_view(),
        name="moderation-price-hide",
    ),
    path(
        "moderation/prices/<uuid:observation_id>/restore/",
        views.RestorePriceView.as_view(),
        name="moderation-price-restore",
    ),
    path(
        "moderation/prices/<uuid:observation_id>/uphold/",
        views.UpholdPriceView.as_view(),
        name="moderation-price-uphold",
    ),
]
