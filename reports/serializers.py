from __future__ import annotations

from rest_framework import serializers

from reports.models import ReportRun, ReportSchedule


class ReportScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportSchedule
        fields = ["id", "dashboard", "frequency", "recipients", "next_run_at", "enabled", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ReportRunSerializer(serializers.ModelSerializer):
    scheduleId = serializers.UUIDField(source="schedule_id")

    class Meta:
        model = ReportRun
        fields = ["id", "scheduleId", "status", "file_url", "generated_at", "error_message", "created_at"]
