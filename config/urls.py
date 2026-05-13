from __future__ import annotations

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from common.views import DatabaseHealthView, HealthView, MetricsView, RedisHealthView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/health/", HealthView.as_view(), name="health"),
    path("api/v1/health/db/", DatabaseHealthView.as_view(), name="health-db"),
    path("api/v1/health/redis/", RedisHealthView.as_view(), name="health-redis"),
    path("api/v1/metrics/", MetricsView.as_view(), name="metrics"),
    path("api/v1/auth/", include("accounts.urls")),
    path("api/v1/organizations/", include("organizations.urls")),
    path("api/v1/api-keys/", include("api_keys.urls")),
    path("api/v1/", include("ingestion.urls")),
    path("api/v1/", include("dashboards.urls")),
    path("api/v1/analytics/", include("analytics.urls")),
    path("api/v1/alerts/", include("alerts.urls")),
    path("api/v1/reports/", include("reports.urls")),
    path("api/v1/billing/", include("billing.urls")),
    path("api/v1/settings/", include("accounts.settings_urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
