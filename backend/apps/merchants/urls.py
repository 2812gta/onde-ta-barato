from django.urls import path

from . import views

urlpatterns = [
    path("merchants/", views.MerchantListCreateView.as_view(), name="merchants"),
    path("merchants/review-queue/", views.ReviewQueueView.as_view(), name="merchant-review-queue"),
    path("merchants/<uuid:merchant_id>/", views.MerchantDetailView.as_view(), name="merchant"),
    path(
        "merchants/<uuid:merchant_id>/verification/",
        views.VerificationView.as_view(),
        name="merchant-verification",
    ),
    path(
        "merchants/<uuid:merchant_id>/members/",
        views.MemberListCreateView.as_view(),
        name="merchant-members",
    ),
    path(
        "merchants/<uuid:merchant_id>/members/<uuid:user_id>/",
        views.MemberDeleteView.as_view(),
        name="merchant-member",
    ),
]
