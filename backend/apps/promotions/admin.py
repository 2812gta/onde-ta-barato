from django.contrib import admin

from .models import Promotion


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ("title", "store", "product_variant", "is_active", "valid_from", "valid_until")
    list_filter = ("is_active",)
    # Rules are validated by the engine; creation and edits go through the audited service.
    readonly_fields = ("rule",)

    def has_add_permission(self, request):  # type: ignore[no-untyped-def]
        return False
