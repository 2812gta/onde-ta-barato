from django.urls import include, path

from . import views

auth_patterns = [
    path("register/", views.RegisterView.as_view(), name="register"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("refresh/", views.RefreshView.as_view(), name="refresh"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("verify-email/", views.VerifyEmailView.as_view(), name="verify-email"),
    path(
        "resend-verification/", views.ResendVerificationView.as_view(), name="resend-verification"
    ),
    path("password-reset/", views.PasswordResetRequestView.as_view(), name="password-reset"),
    path(
        "password-reset/confirm/",
        views.PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
]

urlpatterns = [
    path("auth/", include(auth_patterns)),
    path("me/", views.MeView.as_view(), name="me"),
    path("me/consents/", views.ConsentView.as_view(), name="consents"),
    path("me/export/", views.ExportView.as_view(), name="export"),
    path("users/<uuid:user_id>/role/", views.RoleChangeView.as_view(), name="user-role"),
    path("audit/", include("apps.audit.urls")),
]
