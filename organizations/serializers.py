from __future__ import annotations

import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from organizations.models import Invitation, Membership, Organization


class OrganizationSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = ["id", "name", "slug", "role", "created_at", "updated_at"]

    def get_role(self, obj: Organization) -> str:
        membership = self.context.get("membership")
        return membership.role if membership else ""


class MembershipSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    name = serializers.CharField(source="user.name", read_only=True)
    avatar = serializers.CharField(source="user.avatar", read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "email", "name", "avatar", "role", "status", "created_at", "updated_at"]
        read_only_fields = ["id", "email", "name", "avatar", "status", "created_at", "updated_at"]


class InvitationSerializer(serializers.ModelSerializer):
    token = serializers.CharField(read_only=True)

    class Meta:
        model = Invitation
        fields = ["id", "email", "role", "accepted_at", "expires_at", "created_at", "token"]
        read_only_fields = ["id", "accepted_at", "expires_at", "created_at", "token"]


class InvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=Membership.Role.choices, default=Membership.Role.VIEWER)

    def validate_role(self, value: str) -> str:
        request = self.context["request"]
        if request.membership.role == Membership.Role.ADMIN and value not in {
            Membership.Role.ANALYST,
            Membership.Role.VIEWER,
        }:
            raise serializers.ValidationError("Admins can invite Analyst or Viewer members only.")
        return value

    def create(self, validated_data: dict):
        organization = self.context["organization"]
        token = secrets.token_urlsafe(32)
        invitation = Invitation.objects.create(
            organization=organization,
            email=validated_data["email"].lower(),
            role=validated_data["role"],
            token_hash=make_password(token),
            expires_at=timezone.now() + timedelta(days=7),
        )
        invitation.token = token
        return invitation


class InvitationAcceptSerializer(serializers.Serializer):
    token = serializers.CharField()

    @transaction.atomic
    def save(self, **kwargs):
        user = self.context["request"].user
        token = self.validated_data["token"]
        invitation = None
        for candidate in Invitation.objects.select_related("organization").filter(
            accepted_at__isnull=True,
            expires_at__gt=timezone.now(),
        ):
            if check_password(token, candidate.token_hash):
                invitation = candidate
                break
        if invitation is None:
            raise serializers.ValidationError({"token": "Invitation token is invalid or expired."})
        if invitation.email.lower() != user.email.lower():
            raise serializers.ValidationError({"token": "Invitation is for a different email address."})
        membership, _ = Membership.objects.update_or_create(
            organization=invitation.organization,
            user=user,
            defaults={"role": invitation.role, "status": Membership.Status.ACTIVE},
        )
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=["accepted_at", "updated_at"])
        return membership


class MemberRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=Membership.Role.choices)

    def validate_role(self, value: str) -> str:
        if value == Membership.Role.OWNER:
            raise serializers.ValidationError("Ownership transfers are not supported by this endpoint.")
        return value


def create_placeholder_user(email: str):
    User = get_user_model()
    user, _ = User.objects.get_or_create(
        email=email.lower(),
        defaults={"name": email.split("@")[0], "avatar": "/avatar-1.jpg", "is_active": True},
    )
    return user
