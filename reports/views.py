from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.conf import settings
from django.http import FileResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsOrgMember, ReadAnyWriteAnalyst
from common.tenancy import ensure_request_organization
from dashboards.models import Dashboard
from reports.models import ReportRun, ReportSchedule
from reports.serializers import ReportRunSerializer, ReportScheduleSerializer


class ReportScheduleListCreateView(APIView):
    permission_classes = [ReadAnyWriteAnalyst]

    def get(self, request):
        organization = ensure_request_organization(request)
        schedules = ReportSchedule.objects.filter(organization=organization).select_related("dashboard").order_by("-created_at")
        return Response(ReportScheduleSerializer(schedules, many=True).data)

    def post(self, request):
        organization = ensure_request_organization(request)
        dashboard_id = request.data.get("dashboard")
        get_object_or_404(Dashboard, pk=dashboard_id, organization=organization)
        serializer = ReportScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        schedule = serializer.save(organization=organization)
        return Response(ReportScheduleSerializer(schedule).data, status=status.HTTP_201_CREATED)


class ReportScheduleDetailView(APIView):
    permission_classes = [ReadAnyWriteAnalyst]

    def get_object(self, request, pk):
        organization = ensure_request_organization(request)
        return get_object_or_404(ReportSchedule, pk=pk, organization=organization)

    def patch(self, request, pk):
        schedule = self.get_object(request, pk)
        serializer = ReportScheduleSerializer(schedule, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(ReportScheduleSerializer(schedule).data)

    def delete(self, request, pk):
        self.get_object(request, pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ReportHistoryView(APIView):
    permission_classes = [IsOrgMember]

    def get(self, request):
        organization = ensure_request_organization(request)
        runs = ReportRun.objects.filter(schedule__organization=organization).select_related("schedule")[:100]
        return Response(ReportRunSerializer(runs, many=True).data)


class ReportRunDownloadView(APIView):
    permission_classes = [IsOrgMember]

    def get(self, request, pk):
        organization = ensure_request_organization(request)
        run = get_object_or_404(ReportRun, pk=pk, schedule__organization=organization)
        if run.status != "completed" or not run.file_url:
            return Response({"detail": "Report artifact is not available."}, status=status.HTTP_404_NOT_FOUND)
        relative_path = run.file_url.replace(settings.MEDIA_URL, "", 1).lstrip("/")
        file_path = settings.MEDIA_ROOT / relative_path
        if not file_path.exists():
            return Response({"detail": "Report artifact is missing."}, status=status.HTTP_404_NOT_FOUND)
        return FileResponse(file_path.open("rb"), as_attachment=True, filename=file_path.name)
