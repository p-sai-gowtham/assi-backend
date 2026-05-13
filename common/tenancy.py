from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied


ACTIVE_MEMBERSHIP_STATUS = "active"


def get_active_membership(user: Any):
    if not user or not user.is_authenticated:
        return None
    return (
        user.memberships.select_related("organization")
        .filter(status=ACTIVE_MEMBERSHIP_STATUS)
        .order_by("created_at")
        .first()
    )


def ensure_request_organization(request: Any):
    organization = getattr(request, "organization", None)
    if organization is not None:
        return organization

    membership = getattr(request, "membership", None) or get_active_membership(request.user)
    if membership is None:
        raise PermissionDenied("Authenticated user does not belong to an organization.")

    request.membership = membership
    request.organization = membership.organization
    request.organization_role = membership.role
    return membership.organization


def ensure_request_membership(request: Any):
    ensure_request_organization(request)
    return request.membership
