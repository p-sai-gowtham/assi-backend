from __future__ import annotations

from django.urls import path

from analytics.views import ProductUsageView, RevenueView, TrafficSourcesView

urlpatterns = [
    path("traffic-sources/", TrafficSourcesView.as_view(), name="analytics-traffic-sources"),
    path("product-usage/", ProductUsageView.as_view(), name="analytics-product-usage"),
    path("revenue/", RevenueView.as_view(), name="analytics-revenue"),
]
