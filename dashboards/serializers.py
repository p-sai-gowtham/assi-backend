from __future__ import annotations

from rest_framework import serializers

from dashboards.models import Dashboard, DashboardTemplate, Widget


class WidgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Widget
        fields = ["id", "dashboard", "type", "title", "position", "query_config", "chart_config", "created_at", "updated_at"]
        read_only_fields = ["id", "dashboard", "created_at", "updated_at"]


class DashboardSerializer(serializers.ModelSerializer):
    widgets = WidgetSerializer(many=True, read_only=True)

    class Meta:
        model = Dashboard
        fields = [
            "id",
            "name",
            "description",
            "visibility",
            "public_token",
            "refresh_interval",
            "widgets",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "public_token", "widgets", "created_at", "updated_at"]


class DashboardTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DashboardTemplate
        fields = ["id", "name", "slug", "description", "widgets", "created_at", "updated_at"]
        read_only_fields = fields
