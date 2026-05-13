from __future__ import annotations

from typing import Iterable

from rest_framework.permissions import SAFE_METHODS, BasePermission

from common.tenancy import ensure_request_membership

ROLE_RANK = {
    "Viewer": 10,
    "Analyst": 20,
    "Admin": 30,
    "Owner": 40,
}


def has_min_role(role: str, minimum: str) -> bool:
    return ROLE_RANK.get(role, 0) >= ROLE_RANK[minimum]


class IsOrgMember(BasePermission):
    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            ensure_request_membership(request)
        except Exception:
            return False
        return True


class HasOrgRole(IsOrgMember):
    required_roles: Iterable[str] = ("Viewer",)

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        role = request.membership.role
        return any(has_min_role(role, required) for required in self.required_roles)


class OrgRolePermission(IsOrgMember):
    read_roles: Iterable[str] = ("Viewer",)
    write_roles: Iterable[str] = ("Viewer",)

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        role = request.membership.role
        required_roles = self.read_roles if request.method in SAFE_METHODS else self.write_roles
        return any(has_min_role(role, required) for required in required_roles)


class IsOwnerOrAdmin(HasOrgRole):
    required_roles = ("Admin",)


class IsOwner(HasOrgRole):
    required_roles = ("Owner",)


class ReadAnyWriteAnalyst(OrgRolePermission):
    read_roles = ("Viewer",)
    write_roles = ("Analyst",)


class ReadAnyWriteAdmin(OrgRolePermission):
    read_roles = ("Viewer",)
    write_roles = ("Admin",)


class ReadAdminWriteOwner(OrgRolePermission):
    read_roles = ("Admin",)
    write_roles = ("Owner",)


class CanManageAPIKeys(IsOwnerOrAdmin):
    pass


class CanManageAlerts(HasOrgRole):
    required_roles = ("Analyst",)


class HasValidAPIKey(BasePermission):
    def has_permission(self, request, view) -> bool:
        api_key = getattr(request, "auth", None)
        if api_key is None or getattr(api_key, "revoked_at", None) is not None:
            return False
        request.organization = api_key.organization
        request.api_key = api_key
        return True
