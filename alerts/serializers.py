from __future__ import annotations

from rest_framework import serializers

from alerts.models import AlertHistory, AlertRule


def parse_duration(value: str | int | None) -> int:
    if value is None:
        return 300
    if isinstance(value, int):
        return value
    units = {"s": 1, "m": 60, "h": 3600}
    suffix = value[-1]
    if suffix in units:
        return int(value[:-1]) * units[suffix]
    return int(value)


def format_duration(seconds: int) -> str:
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


class AlertRuleSerializer(serializers.ModelSerializer):
    duration = serializers.SerializerMethodField()
    lastTriggered = serializers.DateTimeField(source="last_triggered", read_only=True)
    mutedUntil = serializers.DateTimeField(source="muted_until", required=False, allow_null=True)
    lastEvaluatedAt = serializers.DateTimeField(source="last_evaluated_at", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = AlertRule
        fields = [
            "id",
            "name",
            "metric",
            "threshold",
            "operator",
            "duration",
            "duration_seconds",
            "enabled",
            "status",
            "severity",
            "channels",
            "lastTriggered",
            "mutedUntil",
            "lastEvaluatedAt",
            "createdAt",
        ]
        read_only_fields = ["id", "createdAt", "lastTriggered", "lastEvaluatedAt"]
        extra_kwargs = {"duration_seconds": {"write_only": True, "required": False}}

    def get_duration(self, obj: AlertRule) -> str:
        return format_duration(obj.duration_seconds)

    def to_internal_value(self, data):
        mutable = dict(data)
        if "duration" in mutable and "duration_seconds" not in mutable:
            mutable["duration_seconds"] = parse_duration(mutable["duration"])
        return super().to_internal_value(mutable)


class AlertHistorySerializer(serializers.ModelSerializer):
    alertId = serializers.UUIDField(source="alert_rule_id")
    triggeredAt = serializers.DateTimeField(source="triggered_at")
    resolvedAt = serializers.DateTimeField(source="resolved_at")
    ruleName = serializers.CharField(source="alert_rule.name", read_only=True)

    class Meta:
        model = AlertHistory
        fields = ["id", "alertId", "ruleName", "triggeredAt", "resolvedAt", "value", "message"]
