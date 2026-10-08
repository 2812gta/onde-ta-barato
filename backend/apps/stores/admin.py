from django.contrib.gis import admin

from .models import Store


@admin.register(Store)
class StoreAdmin(admin.GISModelAdmin):
    list_display = ("name", "store_type", "city", "merchant", "status", "source")
    list_filter = ("store_type", "status", "source")
    search_fields = ("name", "street", "neighborhood")
