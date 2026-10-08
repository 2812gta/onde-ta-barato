from django.urls import path

from . import views

urlpatterns = [
    path("categories/", views.CategoryListView.as_view(), name="categories"),
    path("variants/", views.VariantListView.as_view(), name="variants"),
    path("variants/<uuid:variant_id>/", views.VariantDetailView.as_view(), name="variant"),
    path("catalog/variants/", views.VariantCreateView.as_view(), name="catalog-variant-create"),
]
