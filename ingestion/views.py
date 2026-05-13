from __future__ import annotations

import logging

from django.conf import settings
from pydantic import ValidationError
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404

from common.authentication import APIKeyAuthentication
from common.permissions import HasValidAPIKey, IsOrgMember
from common.permissions import has_min_role
from common.tenancy import ensure_request_membership, ensure_request_organization
from ingestion.models import DataSource, Event, IngestionJob
from ingestion.schemas import BatchEventPayload, EventPayload
from ingestion.serializers import EventSerializer, IngestionJobSerializer
from ingestion.services import create_event, create_events, random_demo_payload
from ingestion.tasks import normalize_event, process_csv_job

logger = logging.getLogger(__name__)


class IngestEventView(APIView):
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [HasValidAPIKey]
    throttle_scope = "ingestion_single"

    def post(self, request):
        try:
            payload = EventPayload.model_validate(request.data)
        except ValidationError as exc:
            return Response({"detail": exc.errors()}, status=status.HTTP_400_BAD_REQUEST)
        event = create_event(organization=request.organization, payload=payload)
        try:
            normalize_event.delay(str(event.id))
        except Exception:
            logger.exception("Failed to enqueue event normalization for %s", event.id)
        return Response(EventSerializer(event).data, status=status.HTTP_201_CREATED)


class IngestEventsView(APIView):
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [HasValidAPIKey]
    throttle_scope = "ingestion_batch"

    def post(self, request):
        try:
            batch = BatchEventPayload.model_validate(request.data)
        except ValidationError as exc:
            return Response({"detail": exc.errors()}, status=status.HTTP_400_BAD_REQUEST)
        events = create_events(organization=request.organization, payloads=batch.events)
        for event in events:
            try:
                normalize_event.delay(str(event.id))
            except Exception:
                logger.exception("Failed to enqueue event normalization for %s", event.id)
        return Response(EventSerializer(events, many=True).data, status=status.HTTP_201_CREATED)


class IngestCSVView(APIView):
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [HasValidAPIKey]
    throttle_scope = "ingestion_csv"

    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": "CSV file is required."}, status=status.HTTP_400_BAD_REQUEST)
        job = IngestionJob.objects.create(
            organization=request.organization,
            source=request.data.get("source", upload.name),
            file=upload,
        )
        try:
            process_csv_job.delay(str(job.id))
        except Exception:
            logger.exception("Failed to enqueue CSV processing job %s", job.id)
        return Response(IngestionJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class WebhookReceiverView(APIView):
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [permissions.AllowAny]
    throttle_scope = "ingestion_single"

    def post(self, request, source_id):
        data_source = get_object_or_404(DataSource, pk=source_id, type=DataSource.Type.WEBHOOK)
        api_key = getattr(request, "auth", None)
        source_secret = request.headers.get("X-Source-Secret", "")
        configured_secret = (data_source.config or {}).get("secret", "")
        if api_key is not None:
            if api_key.revoked_at is not None or api_key.organization_id != data_source.organization_id:
                return Response({"detail": "Invalid API key for this source."}, status=status.HTTP_403_FORBIDDEN)
        elif not configured_secret or source_secret != configured_secret:
            return Response({"detail": "Webhook source authentication failed."}, status=status.HTTP_403_FORBIDDEN)
        try:
            payload = EventPayload.model_validate(request.data)
        except ValidationError as exc:
            return Response({"detail": exc.errors()}, status=status.HTTP_400_BAD_REQUEST)
        event = create_event(organization=data_source.organization, payload=payload, data_source=data_source)
        try:
            normalize_event.delay(str(event.id))
        except Exception:
            logger.exception("Failed to enqueue event normalization for %s", event.id)
        return Response(EventSerializer(event).data, status=status.HTTP_201_CREATED)


class IngestionJobsView(APIView):
    permission_classes = [IsOrgMember]

    def get(self, request):
        organization = ensure_request_organization(request)
        jobs = IngestionJob.objects.filter(organization=organization).order_by("-created_at")[:100]
        return Response(IngestionJobSerializer(jobs, many=True).data)


class EventsView(APIView):
    permission_classes = [IsOrgMember]

    def get(self, request):
        organization = ensure_request_organization(request)
        limit = min(int(request.query_params.get("limit", 50)), 100)
        queryset = Event.objects.filter(organization=organization)
        event_type = request.query_params.get("type")
        if event_type and event_type != "all":
            queryset = queryset.filter(event_type=event_type)
        search = request.query_params.get("search")
        if search:
            queryset = queryset.filter(message__icontains=search) | queryset.filter(external_user_id__icontains=search)
            queryset = queryset.filter(organization=organization)
        cursor = request.query_params.get("cursor")
        if cursor:
            queryset = queryset.filter(timestamp__lt=cursor)
        events = list(queryset.order_by("-timestamp")[: limit + 1])
        next_cursor = events[-1].timestamp.isoformat() if len(events) > limit else None
        results = events[:limit]
        return Response({"results": EventSerializer(results, many=True).data, "next": next_cursor})


class DemoEventView(APIView):
    permission_classes = [IsOrgMember]

    def post(self, request):
        membership = ensure_request_membership(request)
        if not settings.DEBUG and not has_min_role(membership.role, "Admin"):
            return Response({"detail": "Demo event generation is disabled."}, status=status.HTTP_403_FORBIDDEN)
        event_type = request.data.get("type") or request.query_params.get("type")
        if event_type and event_type not in {"pageview", "login", "purchase", "signup", "api_call", "error", "export"}:
            return Response({"detail": "Unsupported event type."}, status=status.HTTP_400_BAD_REQUEST)
        payload = random_demo_payload(force_type=event_type)
        event = create_event(organization=membership.organization, payload=payload)
        return Response(EventSerializer(event).data, status=status.HTTP_201_CREATED)
