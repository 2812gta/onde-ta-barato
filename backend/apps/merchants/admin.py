from django.contrib import admin

from .models import Merchant, MerchantMembership, MerchantVerification


@admin.register(Merchant)
class MerchantAdmin(admin.ModelAdmin):
    list_display = ("trade_name", "cnpj", "status", "verified_at")
    list_filter = ("status",)
    search_fields = ("trade_name", "legal_name", "cnpj")
    # Status changes must go through the audited service, never the admin form.
    readonly_fields = ("status", "verified_at")


@admin.register(MerchantMembership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("merchant", "user", "role")


@admin.register(MerchantVerification)
class VerificationAdmin(admin.ModelAdmin):
    list_display = ("merchant", "from_status", "to_status", "actor", "created_at")

    def has_add_permission(self, request):  # type: ignore[no-untyped-def]
        return False

    def has_change_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False

    def has_delete_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False
