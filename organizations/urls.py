from __future__ import annotations

from django.urls import path

from organizations.views import (
    CurrentOrganizationView,
    InvitationAcceptView,
    OrganizationInvitationsView,
    OrganizationMemberDetailView,
    OrganizationMembersView,
)

urlpatterns = [
    path("current/", CurrentOrganizationView.as_view(), name="organization-current"),
    path("members/", OrganizationMembersView.as_view(), name="organization-members"),
    path("members/<uuid:pk>/", OrganizationMemberDetailView.as_view(), name="organization-member-detail"),
    path("invitations/", OrganizationInvitationsView.as_view(), name="organization-invitations"),
    path("invitations/accept/", InvitationAcceptView.as_view(), name="organization-invitation-accept"),
]
