"""Role-based access control. Permissions are named; roles map to sets of them.

Self-service actions (own profile, own consents) only require authentication and are
not listed here. New permissions are added by the milestone that introduces them.
"""

from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from .models import Role

USERS_VIEW = "users.view"
USERS_MANAGE = "users.manage"
USERS_CHANGE_ROLE = "users.change_role"
AUDIT_VIEW = "audit.view"

ALL_PERMISSIONS = frozenset({USERS_VIEW, USERS_MANAGE, USERS_CHANGE_ROLE, AUDIT_VIEW})

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    Role.CUSTOMER: frozenset(),
    Role.MERCHANT_OWNER: frozenset(),
    Role.MERCHANT_MANAGER: frozenset(),
    Role.MERCHANT_OPERATOR: frozenset(),
    Role.MODERATOR: frozenset({USERS_VIEW}),
    Role.SUPPORT: frozenset({USERS_VIEW}),
    Role.ADMIN: frozenset({USERS_VIEW, USERS_MANAGE, AUDIT_VIEW}),
    Role.SUPERADMIN: ALL_PERMISSIONS,
}


def has_permission(user: Any, permission: str) -> bool:
    if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return False
    return permission in ROLE_PERMISSIONS.get(user.role, frozenset())


def require(permission: str) -> type[BasePermission]:
    """Build a DRF permission class requiring a named RBAC permission."""

    class _Require(BasePermission):
        def has_permission(self, request: Request, view: APIView) -> bool:
            return has_permission(request.user, permission)

    _Require.__name__ = f"Require[{permission}]"
    return _Require
