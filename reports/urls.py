from __future__ import annotations

from django.urls import path

from reports.views import ReportHistoryView, ReportRunDownloadView, ReportScheduleDetailView, ReportScheduleListCreateView

urlpatterns = [
    path("schedules/", ReportScheduleListCreateView.as_view(), name="report-schedule-list-create"),
    path("schedules/<uuid:pk>/", ReportScheduleDetailView.as_view(), name="report-schedule-detail"),
    path("history/", ReportHistoryView.as_view(), name="report-history"),
    path("runs/<uuid:pk>/download/", ReportRunDownloadView.as_view(), name="report-run-download"),
]
