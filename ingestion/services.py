from __future__ import annotations

import logging
import random
from datetime import timedelta
from typing import Iterable

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from billing.models import UsageCounter
from common.realtime import broadcast, dashboard_group, organization_group
from dashboards.models import Dashboard
from ingestion.models import DataSource, Event
from ingestion.schemas import EventPayload
from ingestion.serializers import EventSerializer
from organizations.models import Organization

logger = logging.getLogger(__name__)

SOURCES = ["Google Search", "Direct", "Social Media", "Referral", "Email"]
FEATURES = [
    "Dashboard Analytics",
    "Report Builder",
    "API Integration",
    "Alert Management",
    "Data Exports",
    "Team Collaboration",
]
COUNTRIES = ["US", "CA", "GB", "DE", "IN", "AU", "BR"]
DEVICES = ["desktop", "mobile", "tablet"]
BROWSERS = ["Chrome", "Safari", "Firefox", "Edge"]


def get_api_data_source(organization: Organization) -> DataSource:
    data_source, _ = DataSource.objects.get_or_create(
        organization=organization,
        type=DataSource.Type.API,
        name="API Ingestion",
        defaults={"config": {}},
    )
    return data_source


def invalidate_analytics_cache(organization_id: str) -> None:
    cache.delete_many(
        [f"overview:{organization_id}:{range_key}" for range_key in ["24h", "7d", "30d", "90d"]]
        + [
            f"traffic_sources:{organization_id}:24h",
            f"traffic_sources:{organization_id}:7d",
            f"traffic_sources:{organization_id}:30d",
            f"traffic_sources:{organization_id}:90d",
            f"product_usage:{organization_id}:24h",
            f"product_usage:{organization_id}:7d",
            f"product_usage:{organization_id}:30d",
            f"product_usage:{organization_id}:90d",
            f"revenue:{organization_id}:12m",
        ]
    )


def update_usage_counters(organization: Organization, events: list[Event]) -> None:
    if not events:
        return
    monthly_events = UsageCounter.objects.filter(organization=organization, label="Monthly Events").first()
    if monthly_events:
        monthly_events.used += len(events)
        monthly_events.save(update_fields=["used", "updated_at"])

    api_calls = UsageCounter.objects.filter(organization=organization, label="API Calls").first()
    if api_calls:
        api_calls.used += sum(1 for event in events if event.event_type == "api_call")
        api_calls.save(update_fields=["used", "updated_at"])

    active_users = UsageCounter.objects.filter(organization=organization, label="Active Users").first()
    if active_users:
        since = timezone.now() - timedelta(days=30)
        active_users.used = (
            Event.objects.filter(organization=organization, timestamp__gte=since)
            .exclude(external_user_id="")
            .values("external_user_id")
            .distinct()
            .count()
        )
        active_users.save(update_fields=["used", "updated_at"])


def enqueue_alert_evaluation(organization_id: str) -> None:
    try:
        from alerts.tasks import evaluate_alert_rules_for_org

        evaluate_alert_rules_for_org.delay(str(organization_id))
    except Exception:
        logger.exception("Failed to enqueue alert evaluation for organization %s", organization_id)


def broadcast_dashboard_invalidation(organization: Organization) -> None:
    payload = {"type": "dashboard.invalidate", "payload": {"organizationId": str(organization.id)}}
    broadcast(organization_group(organization.id, "dashboard"), payload)
    for dashboard in Dashboard.objects.filter(organization=organization).only("id"):
        broadcast(dashboard_group(organization.id, dashboard.id), payload)


def post_events_created(organization: Organization, events: list[Event]) -> None:
    if not events:
        return
    invalidate_analytics_cache(str(organization.id))
    update_usage_counters(organization, events)
    for event in events:
        broadcast(
            organization_group(event.organization_id, "events"),
            {
                "type": "event.created",
                "payload": EventSerializer(event).data,
            },
        )
    broadcast_dashboard_invalidation(organization)
    enqueue_alert_evaluation(str(organization.id))


@transaction.atomic
def create_event(*, organization: Organization, payload: EventPayload, data_source: DataSource | None = None) -> Event:
    data_source = data_source or get_api_data_source(organization)
    event = Event.objects.create(
        organization=organization,
        data_source=data_source,
        event_type=payload.type,
        external_user_id=payload.user_id,
        message=payload.message,
        timestamp=payload.timestamp,
        properties=payload.metadata,
        ip_address=payload.ip or payload.metadata.get("ip"),
    )
    transaction.on_commit(lambda: post_events_created(organization, [event]))
    return event


@transaction.atomic
def create_events(*, organization: Organization, payloads: Iterable[EventPayload]) -> list[Event]:
    data_source = get_api_data_source(organization)
    events = [
        Event(
            organization=organization,
            data_source=data_source,
            event_type=payload.type,
            external_user_id=payload.user_id,
            message=payload.message,
            timestamp=payload.timestamp,
            properties=payload.metadata,
            ip_address=payload.ip or payload.metadata.get("ip"),
        )
        for payload in payloads
    ]
    created = list(Event.objects.bulk_create(events, batch_size=500))
    transaction.on_commit(lambda: post_events_created(organization, created))
    return created


def random_demo_payload(force_type: str | None = None) -> EventPayload:
    event_type = force_type or random.choices(
        ["pageview", "login", "purchase", "signup", "api_call", "error", "export"],
        weights=[35, 15, 10, 8, 20, 7, 5],
        k=1,
    )[0]
    feature = random.choice(FEATURES)
    metadata = {
        "source": random.choice(SOURCES),
        "feature": feature,
        "country": random.choice(COUNTRIES),
        "device": random.choice(DEVICES),
        "browser": random.choice(BROWSERS),
    }
    if event_type == "api_call":
        metadata["latency_ms"] = random.choice([120, 180, 240, 380, 620, 900])
    if event_type == "purchase":
        metadata["amount"] = random.choice([29, 49, 99, 199, 299, 499])
    message_by_type = {
        "pageview": f"/{feature.lower().replace(' ', '-')}",
        "login": "User logged in",
        "purchase": "Subscription purchase",
        "signup": "New user signup",
        "api_call": "POST /api/v1/query",
        "error": random.choice(["500 API error", "Dashboard render error", "Webhook timeout"]),
        "export": "CSV export completed",
    }
    return EventPayload.model_validate(
        {
            "type": event_type,
            "userId": f"usr-demo-{random.randint(1, 250):03d}",
            "message": message_by_type[event_type],
            "timestamp": timezone.now().isoformat(),
            "metadata": metadata,
        }
    )
