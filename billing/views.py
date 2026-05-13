from __future__ import annotations

from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.models import Invoice, Subscription, UsageCounter
from billing.serializers import InvoiceSerializer, UsageCounterSerializer
from common.permissions import IsOwnerOrAdmin
from common.tenancy import ensure_request_organization


class BillingSummaryView(APIView):
    permission_classes = [IsOwnerOrAdmin]

    def get(self, request):
        organization = ensure_request_organization(request)
        subscription = Subscription.objects.select_related("plan").filter(organization=organization).first()
        if subscription is None:
            return Response({"plan": None})
        today = timezone.localdate()
        return Response(
            {
                "plan": {
                    "name": subscription.plan.name,
                    "status": subscription.status,
                    "priceMonthly": float(subscription.plan.price_monthly),
                    "priceAnnual": float(subscription.plan.price_annual),
                    "billingPeriod": subscription.billing_period,
                    "nextBillingDate": subscription.current_period_end.isoformat(),
                    "daysRemaining": max((subscription.current_period_end - today).days, 0),
                }
            }
        )


class BillingInvoicesView(APIView):
    permission_classes = [IsOwnerOrAdmin]

    def get(self, request):
        organization = ensure_request_organization(request)
        invoices = Invoice.objects.filter(organization=organization)
        return Response(InvoiceSerializer(invoices, many=True).data)


class BillingUsageView(APIView):
    permission_classes = [IsOwnerOrAdmin]

    def get(self, request):
        organization = ensure_request_organization(request)
        usage = UsageCounter.objects.filter(organization=organization).order_by("created_at")
        return Response(UsageCounterSerializer(usage, many=True).data)
