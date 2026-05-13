from __future__ import annotations

from django.db import models

from common.models import SoftDeleteModel, UUIDTimestampModel
from dashboards.models import Dashboard
from organizations.models import Organization


class ReportSchedule(SoftDeleteModel):
    class Frequency(models.TextChoices):
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="report_schedules")
    dashboard = models.ForeignKey(Dashboard, on_delete=models.CASCADE, related_name="report_schedules")
    frequency = models.CharField(max_length=20, choices=Frequency.choices)
    recipients = models.JSONField(default=list, blank=True)
    next_run_at = models.DateTimeField()
    enabled = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"{self.dashboard.name} {self.frequency}"


class ReportRun(UUIDTimestampModel):
    schedule = models.ForeignKey(ReportSchedule, on_delete=models.CASCADE, related_name="runs")
    status = models.CharField(max_length=32, default="pending")
    file_url = models.URLField(blank=True, default="")
    generated_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.schedule_id}: {self.status}"
