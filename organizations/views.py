from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import permissions
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsOrgMember, IsOwnerOrAdmin, ReadAnyWriteAdmin
from common.tenancy import ensure_request_membership, ensure_request_organization
from organizations.models import Invitation, Membership
from organizations.serializers import (
    InvitationAcceptSerializer,
    InvitationCreateSerializer,
    InvitationSerializer,
    MemberRoleSerializer,
    MembershipSerializer,
    OrganizationSerializer,
)


class CurrentOrganizationView(APIView):
    permission_classes = [IsOrgMember]

    def get(self, request):
        membership = ensure_request_membership(request)
        return Response(
            OrganizationSerializer(
                membership.organization,
                context={"membership": membership},
            ).data
        )


class OrganizationMembersView(APIView):
    permission_classes = [IsOrgMember]

    def get(self, request):
        organization = ensure_request_organization(request)
        members = (
            Membership.objects.select_related("user")
            .filter(organization=organization)
            .order_by("user__name", "user__email")
        )
        return Response(MembershipSerializer(members, many=True).data)


class OrganizationMemberDetailView(APIView):
    permission_classes = [IsOwnerOrAdmin]

    def patch(self, request, pk):
        organization = ensure_request_organization(request)
        membership = get_object_or_404(Membership, pk=pk, organization=organization)
        serializer = MemberRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if membership.role == Membership.Role.OWNER:
            return Response({"detail": "Owner role cannot be changed here."}, status=status.HTTP_400_BAD_REQUEST)
        if request.membership.role == Membership.Role.ADMIN and serializer.validated_data["role"] not in {
            Membership.Role.ANALYST,
            Membership.Role.VIEWER,
        }:
            return Response({"detail": "Admins can assign Analyst or Viewer roles only."}, status=status.HTTP_403_FORBIDDEN)
        membership.role = serializer.validated_data["role"]
        membership.save(update_fields=["role", "updated_at"])
        return Response(MembershipSerializer(membership).data)

    def delete(self, request, pk):
        organization = ensure_request_organization(request)
        membership = get_object_or_404(Membership, pk=pk, organization=organization)
        if membership.role == Membership.Role.OWNER:
            return Response({"detail": "Owner cannot be removed."}, status=status.HTTP_400_BAD_REQUEST)
        membership.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class OrganizationInvitationsView(APIView):
    permission_classes = [ReadAnyWriteAdmin]

    def get(self, request):
        organization = ensure_request_organization(request)
        invitations = Invitation.objects.filter(organization=organization).order_by("-created_at")
        return Response(InvitationSerializer(invitations, many=True).data)

    def post(self, request):
        organization = ensure_request_organization(request)
        serializer = InvitationCreateSerializer(
            data=request.data,
            context={"request": request, "organization": organization},
        )
        serializer.is_valid(raise_exception=True)
        invitation = serializer.save()
        return Response(InvitationSerializer(invitation).data, status=status.HTTP_201_CREATED)


class InvitationAcceptView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = InvitationAcceptSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        membership = serializer.save()
        return Response(MembershipSerializer(membership).data)
