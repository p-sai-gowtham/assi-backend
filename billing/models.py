from __future__ import annotations

from django.db import models

from common.models import UUIDTimestampModel
from organizations.models import Organization


class Plan(UUIDTimestampModel):
    name = models.CharField(max_length=255, unique=True)
    price_monthly = models.DecimalField(max_digits=10, decimal_places=2)
    price_annual = models.DecimalField(max_digits=10, decimal_places=2)
    features = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return self.name


class Subscription(UUIDTimestampModel):
    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=32, default="active")
    billing_period = models.CharField(max_length=20, default="annual")
    current_period_start = models.DateField()
    current_period_end = models.DateField()

    def __str__(self) -> str:
        return f"{self.organization.name}: {self.plan.name}"


class Invoice(UUIDTimestampModel):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="invoices")
    invoice_number = models.CharField(max_length=64)
    date = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=32, default="paid")
    plan_name = models.CharField(max_length=255)
    file_url = models.URLField(blank=True, default="")

    class Meta:
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "invoice_number"], name="unique_org_invoice_number"),
        ]

    def __str__(self) -> str:
        return self.invoice_number


class UsageCounter(UUIDTimestampModel):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="usage_counters")
    label = models.CharField(max_length=128)
    used = models.FloatField(default=0)
    limit = models.FloatField(default=0)
    unit = models.CharField(max_length=64)
    color = models.CharField(max_length=16, default="#3B82F6")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "label"], name="unique_org_usage_label"),
        ]

    def __str__(self) -> str:
        return self.label
