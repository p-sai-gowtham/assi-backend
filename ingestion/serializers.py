from __future__ import annotations

from rest_framework import serializers

from ingestion.models import Event, IngestionJob


class EventSerializer(serializers.ModelSerializer):
    type = serializers.CharField(source="event_type")
    userId = serializers.CharField(source="external_user_id")
    metadata = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = ["id", "timestamp", "type", "userId", "message", "metadata"]

    def get_metadata(self, obj: Event) -> dict:
        metadata = dict(obj.properties or {})
        if obj.ip_address:
            metadata.setdefault("ip", obj.ip_address)
        return metadata


class IngestionJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = IngestionJob
        fields = [
            "id",
            "source",
            "status",
            "total_rows",
            "processed_rows",
            "failed_rows",
            "row_errors",
            "error_message",
            "created_at",
            "updated_at",
        ]
