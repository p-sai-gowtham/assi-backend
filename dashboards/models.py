from __future__ import annotations

import secrets

from django.db import models

from common.models import SoftDeleteModel, UUIDTimestampModel
from organizations.models import Organization


class Dashboard(SoftDeleteModel):
    class Visibility(models.TextChoices):
        TEAM = "team", "Team"
        PUBLIC = "public", "Public"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="dashboards")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    visibility = models.CharField(max_length=20, choices=Visibility.choices, default=Visibility.TEAM)
    public_token = models.CharField(max_length=64, blank=True, default="")
    refresh_interval = models.PositiveIntegerField(default=60)

    def save(self, *args, **kwargs):
        if self.visibility == self.Visibility.PUBLIC and not self.public_token:
            self.public_token = secrets.token_urlsafe(24)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


class Widget(SoftDeleteModel):
    class Type(models.TextChoices):
        LINE = "line", "Line"
        BAR = "bar", "Bar"
        DOUGHNUT = "doughnut", "Doughnut"
        AREA = "area", "Area"
        KPI = "kpi", "KPI"
        TABLE = "table", "Table"

    dashboard = models.ForeignKey(Dashboard, on_delete=models.CASCADE, related_name="widgets")
    type = models.CharField(max_length=20, choices=Type.choices)
    title = models.CharField(max_length=255)
    position = models.JSONField(default=dict)
    query_config = models.JSONField(default=dict, blank=True)
    chart_config = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["position", "created_at"]

    def __str__(self) -> str:
        return self.title


class DashboardTemplate(UUIDTimestampModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True, default="")
    widgets = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class SavedQuery(UUIDTimestampModel):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="saved_queries")
    name = models.CharField(max_length=255)
    metric = models.CharField(max_length=128)
    aggregation = models.CharField(max_length=64)
    group_by = models.CharField(max_length=128, blank=True, default="")
    filters = models.JSONField(default=dict, blank=True)
    time_range = models.CharField(max_length=32, default="7d")

    def __str__(self) -> str:
        return self.name
