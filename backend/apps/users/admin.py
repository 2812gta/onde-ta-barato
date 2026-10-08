from django.contrib import admin

from .models import Consent, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "role", "is_active", "email_verified_at", "created_at")
    list_filter = ("role", "is_active")
    search_fields = ("email",)
    readonly_fields = ("password", "last_login", "created_at", "updated_at", "anonymized_at")
    exclude = ("groups", "user_permissions")


@admin.register(Consent)
class ConsentAdmin(admin.ModelAdmin):
    list_display = ("user", "purpose", "granted", "policy_version", "created_at")
    list_filter = ("purpose", "granted")

    def has_change_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False

    def has_delete_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False
