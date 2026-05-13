from __future__ import annotations

from django.urls import path

from dashboards.views import (
    DashboardDetailView,
    DashboardDataView,
    DashboardListCreateView,
    DashboardOverviewView,
    DashboardTemplateInstantiateView,
    DashboardTemplateListView,
    DashboardWidgetsView,
    PublicDashboardView,
    WidgetDetailView,
)

urlpatterns = [
    path("dashboard/overview/", DashboardOverviewView.as_view(), name="dashboard-overview"),
    path("dashboards/", DashboardListCreateView.as_view(), name="dashboard-list-create"),
    path("dashboards/templates/", DashboardTemplateListView.as_view(), name="dashboard-template-list"),
    path("dashboards/templates/<uuid:template_id>/instantiate/", DashboardTemplateInstantiateView.as_view(), name="dashboard-template-instantiate"),
    path("dashboards/<uuid:pk>/", DashboardDetailView.as_view(), name="dashboard-detail"),
    path("dashboards/<uuid:pk>/data/", DashboardDataView.as_view(), name="dashboard-data"),
    path("dashboards/<uuid:dashboard_id>/widgets/", DashboardWidgetsView.as_view(), name="dashboard-widgets"),
    path("widgets/<uuid:pk>/", WidgetDetailView.as_view(), name="widget-detail"),
    path("public/dashboards/<str:public_token>/", PublicDashboardView.as_view(), name="public-dashboard"),
]
