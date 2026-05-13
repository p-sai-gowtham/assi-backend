from __future__ import annotations

from django.db import models

from common.models import SoftDeleteModel, UUIDTimestampModel
from organizations.models import Organization


class AlertRule(SoftDeleteModel):
    class Operator(models.TextChoices):
        GT = ">", ">"
        LT = "<", "<"
        EQ = "==", "=="
        GTE = ">=", ">="
        LTE = "<=", "<="

    class Status(models.TextChoices):
        ACTIVE = "Active", "Active"
        TRIGGERED = "Triggered", "Triggered"
        RESOLVED = "Resolved", "Resolved"
        MUTED = "Muted", "Muted"

    class Severity(models.TextChoices):
        CRITICAL = "critical", "Critical"
        WARNING = "warning", "Warning"
        INFO = "info", "Info"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="alert_rules")
    name = models.CharField(max_length=255)
    metric = models.CharField(max_length=128)
    operator = models.CharField(max_length=4, choices=Operator.choices)
    threshold = models.FloatField()
    duration_seconds = models.PositiveIntegerField(default=300)
    enabled = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.INFO)
    channels = models.JSONField(default=list, blank=True)
    last_triggered = models.DateTimeField(null=True, blank=True)
    muted_until = models.DateTimeField(null=True, blank=True)
    last_evaluated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["organization", "status"])]

    def __str__(self) -> str:
        return self.name


class AlertHistory(UUIDTimestampModel):
    alert_rule = models.ForeignKey(AlertRule, on_delete=models.CASCADE, related_name="history")
    triggered_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)
    value = models.FloatField()
    message = models.TextField()

    class Meta:
        ordering = ["-triggered_at"]

    def __str__(self) -> str:
        return self.message


class NotificationChannel(UUIDTimestampModel):
    class Type(models.TextChoices):
        IN_APP = "in_app", "In-app"
        EMAIL = "email", "Email"
        WEBHOOK = "webhook", "Webhook"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="notification_channels")
    type = models.CharField(max_length=20, choices=Type.choices)
    config = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"{self.type} channel"


class NotificationDelivery(UUIDTimestampModel):
    channel = models.ForeignKey(NotificationChannel, on_delete=models.CASCADE, related_name="deliveries")
    alert_history = models.ForeignKey(AlertHistory, on_delete=models.CASCADE, related_name="deliveries")
    status = models.CharField(max_length=32, default="pending")
    response_body = models.TextField(blank=True, default="")

    def __str__(self) -> str:
        return f"{self.channel_id}: {self.status}"
