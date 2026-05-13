from __future__ import annotations

from django.contrib.postgres.indexes import GinIndex
from django.db import models

from common.models import UUIDTimestampModel
from organizations.models import Organization


class DataSource(UUIDTimestampModel):
    class Type(models.TextChoices):
        API = "api", "API"
        CSV = "csv", "CSV"
        WEBHOOK = "webhook", "Webhook"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="data_sources")
    type = models.CharField(max_length=20, choices=Type.choices)
    name = models.CharField(max_length=255)
    config = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return self.name


class Event(UUIDTimestampModel):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="events")
    data_source = models.ForeignKey(DataSource, on_delete=models.SET_NULL, null=True, blank=True, related_name="events")
    event_type = models.CharField(max_length=64)
    external_user_id = models.CharField(max_length=255, blank=True, default="")
    message = models.TextField(blank=True, default="")
    timestamp = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)
    properties = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "-timestamp"], name="event_org_ts_idx"),
            models.Index(fields=["organization", "event_type", "-timestamp"], name="event_org_type_ts_idx"),
            GinIndex(fields=["properties"], name="event_properties_gin_idx"),
        ]
        ordering = ["-timestamp"]

    def __str__(self) -> str:
        return f"{self.event_type} at {self.timestamp}"


class IngestionJob(UUIDTimestampModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="ingestion_jobs")
    source = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    file = models.FileField(upload_to="ingestion/", null=True, blank=True)
    total_rows = models.PositiveIntegerField(default=0)
    processed_rows = models.PositiveIntegerField(default=0)
    failed_rows = models.PositiveIntegerField(default=0)
    row_errors = models.JSONField(default=list, blank=True)
    error_message = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.source} ({self.status})"
