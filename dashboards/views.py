from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from analytics.services import overview_widgets, widget_data
from common.permissions import IsOrgMember, ReadAnyWriteAnalyst
from common.realtime import broadcast, dashboard_group, organization_group
from common.tenancy import ensure_request_organization
from dashboards.models import Dashboard, DashboardTemplate, Widget
from dashboards.serializers import DashboardSerializer, DashboardTemplateSerializer, WidgetSerializer


def broadcast_dashboard_update(dashboard: Dashboard) -> None:
    message = {"type": "dashboard.updated", "payload": {"id": str(dashboard.id)}}
    broadcast(organization_group(dashboard.organization_id, "dashboard"), message)
    broadcast(dashboard_group(dashboard.organization_id, dashboard.id), message)


class DashboardOverviewView(APIView):
    permission_classes = [IsOrgMember]
    throttle_scope = "dashboard_queries"

    def get(self, request):
        organization = ensure_request_organization(request)
        return Response(overview_widgets(organization, request.query_params.get("range", "7d")))


class DashboardListCreateView(APIView):
    permission_classes = [ReadAnyWriteAnalyst]

    def get(self, request):
        organization = ensure_request_organization(request)
        dashboards = Dashboard.objects.filter(organization=organization).prefetch_related("widgets").order_by("name")
        return Response(DashboardSerializer(dashboards, many=True).data)

    def post(self, request):
        organization = ensure_request_organization(request)
        serializer = DashboardSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dashboard = serializer.save(organization=organization)
        broadcast_dashboard_update(dashboard)
        return Response(DashboardSerializer(dashboard).data, status=status.HTTP_201_CREATED)


class DashboardDetailView(APIView):
    permission_classes = [ReadAnyWriteAnalyst]

    def get_object(self, request, pk):
        organization = ensure_request_organization(request)
        return get_object_or_404(Dashboard, pk=pk, organization=organization)

    def get(self, request, pk):
        return Response(DashboardSerializer(self.get_object(request, pk)).data)

    def patch(self, request, pk):
        dashboard = self.get_object(request, pk)
        serializer = DashboardSerializer(dashboard, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        broadcast_dashboard_update(dashboard)
        return Response(DashboardSerializer(dashboard).data)

    def delete(self, request, pk):
        dashboard = self.get_object(request, pk)
        dashboard.delete()
        broadcast_dashboard_update(dashboard)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DashboardWidgetsView(APIView):
    permission_classes = [ReadAnyWriteAnalyst]

    def get_dashboard(self, request, dashboard_id):
        organization = ensure_request_organization(request)
        return get_object_or_404(Dashboard, pk=dashboard_id, organization=organization)

    def get(self, request, dashboard_id):
        dashboard = self.get_dashboard(request, dashboard_id)
        return Response(WidgetSerializer(dashboard.widgets.all(), many=True).data)

    def post(self, request, dashboard_id):
        dashboard = self.get_dashboard(request, dashboard_id)
        serializer = WidgetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        widget = serializer.save(dashboard=dashboard)
        broadcast_dashboard_update(dashboard)
        return Response(WidgetSerializer(widget).data, status=status.HTTP_201_CREATED)


class WidgetDetailView(APIView):
    permission_classes = [ReadAnyWriteAnalyst]

    def get_object(self, request, pk):
        organization = ensure_request_organization(request)
        return get_object_or_404(Widget, pk=pk, dashboard__organization=organization)

    def get(self, request, pk):
        return Response(WidgetSerializer(self.get_object(request, pk)).data)

    def patch(self, request, pk):
        widget = self.get_object(request, pk)
        serializer = WidgetSerializer(widget, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        broadcast_dashboard_update(widget.dashboard)
        return Response(WidgetSerializer(widget).data)

    def delete(self, request, pk):
        widget = self.get_object(request, pk)
        dashboard = widget.dashboard
        widget.delete()
        broadcast_dashboard_update(dashboard)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DashboardDataView(APIView):
    permission_classes = [IsOrgMember]
    throttle_scope = "dashboard_queries"

    def get(self, request, pk):
        organization = ensure_request_organization(request)
        dashboard = get_object_or_404(Dashboard, pk=pk, organization=organization)
        range_key = request.query_params.get("range", "7d")
        payload = DashboardSerializer(dashboard).data
        payload["widgets"] = [
            WidgetSerializer(widget).data | {
                "data": widget_data(organization, widget.type, widget.query_config, range_key),
            }
            for widget in dashboard.widgets.all()
        ]
        return Response(payload)


class PublicDashboardView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, public_token):
        dashboard = get_object_or_404(
            Dashboard.objects.select_related("organization").prefetch_related("widgets"),
            public_token=public_token,
            visibility=Dashboard.Visibility.PUBLIC,
        )
        range_key = request.query_params.get("range", "7d")
        payload = DashboardSerializer(dashboard).data
        payload["widgets"] = [
            WidgetSerializer(widget).data | {
                "data": widget_data(dashboard.organization, widget.type, widget.query_config, range_key),
            }
            for widget in dashboard.widgets.all()
        ]
        return Response(payload)


class DashboardTemplateListView(APIView):
    permission_classes = [IsOrgMember]

    def get(self, request):
        templates = DashboardTemplate.objects.filter(is_active=True)
        return Response(DashboardTemplateSerializer(templates, many=True).data)


class DashboardTemplateInstantiateView(APIView):
    permission_classes = [ReadAnyWriteAnalyst]

    def post(self, request, template_id):
        organization = ensure_request_organization(request)
        template = get_object_or_404(DashboardTemplate, pk=template_id, is_active=True)
        dashboard = Dashboard.objects.create(
            organization=organization,
            name=request.data.get("name") or template.name,
            description=template.description,
            refresh_interval=int(request.data.get("refresh_interval") or 60),
        )
        for index, widget_config in enumerate(template.widgets or []):
            Widget.objects.create(
                dashboard=dashboard,
                type=widget_config.get("type", Widget.Type.LINE),
                title=widget_config.get("title", "Widget"),
                position=widget_config.get("position") or {"x": index % 2, "y": index // 2},
                query_config=widget_config.get("query_config") or {},
                chart_config=widget_config.get("chart_config") or {},
            )
        broadcast_dashboard_update(dashboard)
        return Response(DashboardSerializer(dashboard).data, status=status.HTTP_201_CREATED)
