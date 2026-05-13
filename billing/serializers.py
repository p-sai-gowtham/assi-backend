from __future__ import annotations

from rest_framework import serializers

from billing.models import Invoice, UsageCounter


class InvoiceSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="invoice_number")
    plan = serializers.CharField(source="plan_name")

    class Meta:
        model = Invoice
        fields = ["id", "date", "amount", "status", "plan", "file_url"]


class UsageCounterSerializer(serializers.ModelSerializer):
    class Meta:
        model = UsageCounter
        fields = ["label", "used", "limit", "unit", "color"]
