from django.contrib import admin

from .models import Brand, Category, Product, ProductVariant


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    search_fields = ("name",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "price_ttl_hours")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "brand", "category", "catalog_source")
    search_fields = ("name", "normalized_name")


@admin.register(ProductVariant)
class VariantAdmin(admin.ModelAdmin):
    list_display = ("product", "label", "quantity", "unit", "gtin")
    search_fields = ("gtin", "product__name")
    readonly_fields = ("base_quantity", "base_unit", "identity_key")
