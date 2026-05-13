from __future__ import annotations

from django.core.cache import cache
from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok"})


class DatabaseHealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return Response({"status": "ok", "database": "ok"})


class RedisHealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        cache_key = "health:redis"
        cache.set(cache_key, "ok", 10)
        return Response({"status": "ok", "redis": cache.get(cache_key)})


class MetricsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        from alerts.models import AlertHistory, AlertRule
        from dashboards.models import Dashboard
        from ingestion.models import Event, IngestionJob
        from organizations.models import Organization
        from reports.models import ReportRun

        return Response(
            {
                "organizations": Organization.objects.count(),
                "events": Event.objects.count(),
                "dashboards": Dashboard.objects.count(),
                "ingestion_jobs": IngestionJob.objects.count(),
                "alert_rules": AlertRule.objects.count(),
                "open_alerts": AlertHistory.objects.filter(resolved_at__isnull=True).count(),
                "report_runs": ReportRun.objects.count(),
            }
        )
