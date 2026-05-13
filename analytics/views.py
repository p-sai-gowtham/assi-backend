from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from analytics import services
from common.permissions import IsOrgMember
from common.tenancy import ensure_request_organization


class TrafficSourcesView(APIView):
    permission_classes = [IsOrgMember]

    def get(self, request):
        return Response(services.traffic_sources(ensure_request_organization(request), request.query_params.get("range", "7d")))


class ProductUsageView(APIView):
    permission_classes = [IsOrgMember]

    def get(self, request):
        return Response(services.product_usage(ensure_request_organization(request), request.query_params.get("range", "7d")))


class RevenueView(APIView):
    permission_classes = [IsOrgMember]

    def get(self, request):
        return Response(services.revenue(ensure_request_organization(request), request.query_params.get("range", "12m")))
