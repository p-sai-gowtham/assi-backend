from __future__ import annotations

from django.urls import path

from billing.views import BillingInvoicesView, BillingSummaryView, BillingUsageView

urlpatterns = [
    path("summary/", BillingSummaryView.as_view(), name="billing-summary"),
    path("invoices/", BillingInvoicesView.as_view(), name="billing-invoices"),
    path("usage/", BillingUsageView.as_view(), name="billing-usage"),
]
