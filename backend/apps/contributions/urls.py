from django.urls import path

from . import views

urlpatterns = [
    path("contributions/", views.ContributionListCreateView.as_view(), name="contributions"),
    path(
        "contributions/<uuid:contribution_id>/",
        views.ContributionDetailView.as_view(),
        name="contribution-detail",
    ),
    path(
        "contributions/<uuid:contribution_id>/confirm/",
        views.ContributionConfirmView.as_view(),
        name="contribution-confirm",
    ),
    path(
        "contributions/<uuid:contribution_id>/cancel/",
        views.ContributionCancelView.as_view(),
        name="contribution-cancel",
    ),
]
