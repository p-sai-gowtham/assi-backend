from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import UserPreference
from alerts.models import NotificationChannel
from common.permissions import IsOrgMember
from common.tenancy import ensure_request_organization


class SettingsView(APIView):
    permission_classes = [IsOrgMember]

    def get(self, request):
        organization = ensure_request_organization(request)
        preferences, _ = UserPreference.objects.get_or_create(user=request.user)
        email_channel, _ = NotificationChannel.objects.get_or_create(
            organization=organization,
            type=NotificationChannel.Type.EMAIL,
            defaults={"enabled": preferences.email_notifications, "config": {"email": request.user.email}},
        )
        in_app_channel, _ = NotificationChannel.objects.get_or_create(
            organization=organization,
            type=NotificationChannel.Type.IN_APP,
            defaults={"enabled": preferences.push_notifications, "config": {}},
        )
        webhook_channel, _ = NotificationChannel.objects.get_or_create(
            organization=organization,
            type=NotificationChannel.Type.WEBHOOK,
            defaults={"enabled": preferences.webhook_enabled, "config": {}},
        )
        return Response(
            {
                "theme": preferences.theme,
                "language": preferences.language,
                "timezone": preferences.timezone,
                "email_notifications": email_channel.enabled,
                "push_notifications": in_app_channel.enabled,
                "slack_enabled": preferences.slack_enabled,
                "webhook_enabled": webhook_channel.enabled,
                "webhook_url": webhook_channel.config.get("url", ""),
                "api_keys_count": organization.api_keys.filter(revoked_at__isnull=True).count(),
                "two_factor_enabled": False,
                "active_sessions": 1,
            }
        )

    def patch(self, request):
        preferences, _ = UserPreference.objects.get_or_create(user=request.user)
        allowed = {
            "theme",
            "language",
            "timezone",
            "email_notifications",
            "push_notifications",
            "slack_enabled",
            "webhook_enabled",
        }
        for key, value in request.data.items():
            if key in allowed:
                setattr(preferences, key, value)
        preferences.save()
        organization = ensure_request_organization(request)
        channel_updates = {
            NotificationChannel.Type.EMAIL: request.data.get("email_notifications"),
            NotificationChannel.Type.IN_APP: request.data.get("push_notifications"),
            NotificationChannel.Type.WEBHOOK: request.data.get("webhook_enabled"),
        }
        for channel_type, enabled in channel_updates.items():
            if enabled is None:
                continue
            channel, _ = NotificationChannel.objects.get_or_create(
                organization=organization,
                type=channel_type,
                defaults={"config": {}},
            )
            channel.enabled = bool(enabled)
            if channel_type == NotificationChannel.Type.EMAIL:
                channel.config = {**channel.config, "email": request.user.email}
            if channel_type == NotificationChannel.Type.WEBHOOK and request.data.get("webhook_url"):
                channel.config = {**channel.config, "url": request.data["webhook_url"]}
            channel.save(update_fields=["enabled", "config", "updated_at"])
        return self.get(request)
