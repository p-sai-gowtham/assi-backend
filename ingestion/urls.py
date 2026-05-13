from __future__ import annotations

from django.urls import path

from ingestion.views import DemoEventView, EventsView, IngestCSVView, IngestEventView, IngestEventsView, IngestionJobsView, WebhookReceiverView

urlpatterns = [
    path("ingest/event/", IngestEventView.as_view(), name="ingest-event"),
    path("ingest/events/", IngestEventsView.as_view(), name="ingest-events"),
    path("ingest/csv/", IngestCSVView.as_view(), name="ingest-csv"),
    path("ingestion/jobs/", IngestionJobsView.as_view(), name="ingestion-jobs"),
    path("webhooks/<uuid:source_id>/", WebhookReceiverView.as_view(), name="webhook-receiver"),
    path("events/", EventsView.as_view(), name="events"),
    path("demo/events/", DemoEventView.as_view(), name="demo-events"),
]
