from __future__ import annotations

from django.contrib.auth import authenticate
from django.db import transaction
from django.utils.text import slugify
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User, UserPreference
from alerts.models import NotificationChannel
from organizations.models import Membership, Organization


def user_payload(user: User, membership: Membership | None = None) -> dict[str, str]:
    membership = membership or user.memberships.select_related("organization").filter(status="active").first()
    organization = membership.organization if membership else None
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "avatar": user.avatar,
        "role": membership.role if membership else "Viewer",
        "organizationId": str(organization.id) if organization else "",
        "organizationName": organization.name if organization else "",
    }


class SignupSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    name = serializers.CharField(max_length=255)
    organizationName = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate_email(self, value: str) -> str:
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value.lower()

    @transaction.atomic
    def create(self, validated_data: dict) -> tuple[User, Membership, RefreshToken]:
        organization_name = validated_data.get("organizationName") or f"{validated_data['name']}'s Organization"
        base_slug = slugify(organization_name) or "organization"
        slug = base_slug
        suffix = 1
        while Organization.objects.filter(slug=slug).exists():
            suffix += 1
            slug = f"{base_slug}-{suffix}"

        user = User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            name=validated_data["name"],
            avatar="/avatar-1.jpg",
        )
        UserPreference.objects.create(user=user)
        organization = Organization.objects.create(name=organization_name, slug=slug)
        membership = Membership.objects.create(
            organization=organization,
            user=user,
            role=Membership.Role.OWNER,
            status=Membership.Status.ACTIVE,
        )
        NotificationChannel.objects.get_or_create(
            organization=organization,
            type=NotificationChannel.Type.IN_APP,
            defaults={"enabled": True, "config": {}},
        )
        NotificationChannel.objects.get_or_create(
            organization=organization,
            type=NotificationChannel.Type.EMAIL,
            defaults={"enabled": True, "config": {"email": user.email}},
        )
        return user, membership, RefreshToken.for_user(user)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs: dict) -> dict:
        user = authenticate(
            request=self.context.get("request"),
            username=attrs["email"].lower(),
            password=attrs["password"],
        )
        if user is None:
            raise serializers.ValidationError("Invalid email or password.")
        if not user.is_active:
            raise serializers.ValidationError("This account is inactive.")
        membership = user.memberships.select_related("organization").filter(status="active").first()
        if membership is None:
            raise serializers.ValidationError("This account is not assigned to an organization.")
        attrs["user"] = user
        attrs["membership"] = membership
        attrs["refresh"] = RefreshToken.for_user(user)
        return attrs


class MeSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "name", "avatar"]
        read_only_fields = ["id", "email"]
