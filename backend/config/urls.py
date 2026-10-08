from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from apps.core.views import HealthView

api_v1 = [
    path("", include("apps.users.urls")),
    path("", include("apps.merchants.urls")),
    path("", include("apps.stores.urls")),
    path("", include("apps.products.urls")),
    path("", include("apps.prices.urls")),
    path("", include("apps.promotions.urls")),
]

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("admin/", admin.site.urls),
    path("api/v1/", include((api_v1, "v1"))),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
