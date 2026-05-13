from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pytest
from channels.testing import WebsocketCommunicator
from channels.layers import get_channel_layer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from alerts.models import AlertHistory, AlertRule, NotificationChannel, NotificationDelivery
from alerts.tasks import evaluate_alert_rules_for_org
from api_keys.models import OrganizationAPIKey
from billing.models import UsageCounter
from common.realtime import organization_group
from config.asgi import application
from dashboards.models import Dashboard, DashboardTemplate, Widget
from ingestion.schemas import EventPayload
from ingestion.services import create_event
from ingestion.models import DataSource, Event, IngestionJob
from organizations.models import Membership, Organization
from reports.models import ReportRun, ReportSchedule
from reports.tasks import process_due_report_schedules


def make_member_client(api_client, organization, role: str):
    User = get_user_model()
    user = User.objects.create_user(email=f"{role.lower()}@example.com", password="Password123!", name=role)
    Membership.objects.create(organization=organization, user=user, role=role)
    api_client.force_authenticate(user=user)
    return api_client, user


@pytest.mark.django_db
def test_signup_creates_org_owner_membership(api_client):
    response = api_client.post(
        "/api/v1/auth/signup/",
        {
            "email": "new@example.com",
            "password": "Password123!",
            "name": "New Owner",
            "organizationName": "NewCo",
        },
        format="json",
    )
    assert response.status_code == 201
    assert response.data["access"]
    assert response.data["user"]["role"] == "Owner"
    user = get_user_model().objects.get(email="new@example.com")
    assert Membership.objects.filter(user=user, role=Membership.Role.OWNER, organization__name="NewCo").exists()


@pytest.mark.django_db
def test_login_returns_frontend_user_shape(api_client, user):
    response = api_client.post(
        "/api/v1/auth/login/",
        {"email": "owner@example.com", "password": "Password123!"},
        format="json",
    )
    assert response.status_code == 200
    assert set(response.data["user"]) == {"id", "email", "name", "avatar", "role", "organizationId", "organizationName"}
    assert response.data["user"]["email"] == user.email


@pytest.mark.django_db
def test_refresh_restores_session(api_client, user):
    login = api_client.post(
        "/api/v1/auth/login/",
        {"email": "owner@example.com", "password": "Password123!"},
        format="json",
    )
    assert login.status_code == 200
    refresh = api_client.post("/api/v1/auth/refresh/", {}, format="json")
    assert refresh.status_code == 200
    assert refresh.data["access"]


@pytest.mark.django_db
def test_logout_clears_refresh_cookie(api_client, user):
    login = api_client.post(
        "/api/v1/auth/login/",
        {"email": "owner@example.com", "password": "Password123!"},
        format="json",
    )
    assert login.status_code == 200
    response = api_client.post("/api/v1/auth/logout/", {}, format="json")
    assert response.status_code == 204
    assert response.cookies["analytics_refresh"].value == ""


@pytest.mark.django_db
def test_tenant_isolation_prevents_cross_org_access(authenticated_client):
    other_org = Organization.objects.create(name="Other", slug="other")
    dashboard = Dashboard.objects.create(organization=other_org, name="Other Dashboard")
    response = authenticated_client.get(f"/api/v1/dashboards/{dashboard.id}/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_role_permissions_for_viewer_analyst_admin_owner(api_client, organization, authenticated_client):
    owner_response = authenticated_client.post("/api/v1/dashboards/", {"name": "Owner Dashboard"}, format="json")
    assert owner_response.status_code == 201

    viewer_client, _ = make_member_client(api_client, organization, Membership.Role.VIEWER)
    assert viewer_client.get("/api/v1/dashboards/").status_code == 200
    assert viewer_client.post("/api/v1/dashboards/", {"name": "Viewer Dashboard"}, format="json").status_code == 403
    assert viewer_client.post("/api/v1/alerts/rules/", {"name": "Viewer Alert"}, format="json").status_code == 403
    assert viewer_client.post("/api/v1/api-keys/", {"name": "Viewer Key"}, format="json").status_code == 403

    analyst_client, _ = make_member_client(api_client, organization, Membership.Role.ANALYST)
    assert analyst_client.post("/api/v1/dashboards/", {"name": "Analyst Dashboard"}, format="json").status_code == 201
    assert analyst_client.post(
        "/api/v1/alerts/rules/",
        {"name": "Analyst Alert", "metric": "sessions", "operator": ">", "threshold": 1, "duration": "1m", "severity": "info", "channels": ["in-app"]},
        format="json",
    ).status_code == 201
    assert analyst_client.post("/api/v1/api-keys/", {"name": "Analyst Key"}, format="json").status_code == 403

    admin_client, _ = make_member_client(api_client, organization, Membership.Role.ADMIN)
    assert admin_client.post("/api/v1/api-keys/", {"name": "Admin Key"}, format="json").status_code == 201
    assert admin_client.post("/api/v1/organizations/invitations/", {"email": "new-admin-invite@example.com", "role": "Viewer"}, format="json").status_code == 201


@pytest.mark.django_db
def test_api_never_trusts_organization_id_from_body(authenticated_client, organization):
    other_org = Organization.objects.create(name="Other Body Org", slug="other-body-org")
    response = authenticated_client.post(
        "/api/v1/dashboards/",
        {"name": "Scoped Dashboard", "organization": str(other_org.id), "organization_id": str(other_org.id)},
        format="json",
    )
    assert response.status_code == 201
    assert Dashboard.objects.get(id=response.data["id"]).organization == organization


@pytest.mark.django_db
def test_api_key_ingestion_works(api_client, api_key):
    key, raw_key = api_key
    response = api_client.post(
        "/api/v1/ingest/event/",
        {
            "event_type": "pageview",
            "external_user_id": "usr-123",
            "message": "/dashboard",
            "properties": {"ip": "127.0.0.1"},
        },
        HTTP_X_API_KEY=raw_key,
        format="json",
    )
    assert response.status_code == 201
    assert Event.objects.filter(organization=key.organization, event_type="pageview").exists()


@pytest.mark.django_db
def test_batch_ingestion_creates_multiple_events(api_client, api_key):
    key, raw_key = api_key
    response = api_client.post(
        "/api/v1/ingest/events/",
        {
            "events": [
                {"event_type": "pageview", "message": "/one"},
                {"event_type": "purchase", "message": "Purchase", "properties": {"amount": 99}},
            ]
        },
        HTTP_X_API_KEY=raw_key,
        format="json",
    )
    assert response.status_code == 201
    assert Event.objects.filter(organization=key.organization).count() == 2


@pytest.mark.django_db
def test_csv_ingestion_creates_events_and_job(api_client, api_key):
    key, raw_key = api_key
    csv_file = SimpleUploadedFile(
        "events.csv",
        b"event_type,external_user_id,message,timestamp,source\npageview,usr-1,/pricing,,Google Search\npurchase,usr-2,Sale,,Email\n",
        content_type="text/csv",
    )
    response = api_client.post("/api/v1/ingest/csv/", {"file": csv_file}, HTTP_X_API_KEY=raw_key, format="multipart")
    assert response.status_code == 202
    job = IngestionJob.objects.get(id=response.data["id"])
    assert job.status == IngestionJob.Status.COMPLETED
    assert job.processed_rows == 2
    assert Event.objects.filter(organization=key.organization).count() == 2


@pytest.mark.django_db
def test_invalid_csv_records_failed_job(api_client, api_key):
    _key, raw_key = api_key
    csv_file = SimpleUploadedFile(
        "bad-events.csv",
        b"event_type,message\nnot_a_real_event,Bad row\n",
        content_type="text/csv",
    )
    response = api_client.post("/api/v1/ingest/csv/", {"file": csv_file}, HTTP_X_API_KEY=raw_key, format="multipart")
    assert response.status_code == 202
    job = IngestionJob.objects.get(id=response.data["id"])
    assert job.status == IngestionJob.Status.FAILED
    assert job.failed_rows == 1
    assert job.row_errors


@pytest.mark.django_db
def test_webhook_receiver_authenticates_source_secret(api_client, organization):
    source = DataSource.objects.create(
        organization=organization,
        type=DataSource.Type.WEBHOOK,
        name="Partner",
        config={"secret": "source-secret"},
    )
    response = api_client.post(
        f"/api/v1/webhooks/{source.id}/",
        {"event_type": "signup", "message": "Webhook signup"},
        HTTP_X_SOURCE_SECRET="source-secret",
        format="json",
    )
    assert response.status_code == 201
    assert Event.objects.filter(data_source=source, event_type="signup").exists()


@pytest.mark.django_db
def test_revoked_api_key_fails(api_client, api_key):
    key, raw_key = api_key
    key.revoke()
    response = api_client.post(
        "/api/v1/ingest/event/",
        {"event_type": "pageview", "message": "/dashboard"},
        HTTP_X_API_KEY=raw_key,
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db(transaction=True)
def test_usage_counters_updated_by_ingestion(api_client, api_key):
    key, raw_key = api_key
    UsageCounter.objects.create(organization=key.organization, label="Monthly Events", used=0, limit=100, unit="events")
    UsageCounter.objects.create(organization=key.organization, label="API Calls", used=0, limit=100, unit="calls")
    UsageCounter.objects.create(organization=key.organization, label="Active Users", used=0, limit=100, unit="users")
    response = api_client.post(
        "/api/v1/ingest/event/",
        {"event_type": "api_call", "external_user_id": "usr-api", "message": "POST", "properties": {"latency_ms": 50}},
        HTTP_X_API_KEY=raw_key,
        format="json",
    )
    assert response.status_code == 201
    assert UsageCounter.objects.get(organization=key.organization, label="Monthly Events").used == 1
    assert UsageCounter.objects.get(organization=key.organization, label="API Calls").used == 1
    assert UsageCounter.objects.get(organization=key.organization, label="Active Users").used == 1


def test_throttle_scopes_are_configured(settings):
    assert settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["auth_login"]
    assert settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["ingestion_single"]
    assert settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["ingestion_csv"]
    assert settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["dashboard_queries"]


@pytest.mark.django_db
def test_dashboard_overview_returns_widgets(authenticated_client, organization):
    Event.objects.create(
        organization=organization,
        event_type="pageview",
        external_user_id="usr-123",
        message="/dashboard",
        timestamp=timezone.now(),
        properties={"source": "Google", "feature": "Dashboard"},
    )
    response = authenticated_client.get("/api/v1/dashboard/overview/?range=7d")
    assert response.status_code == 200
    assert isinstance(response.data, list)
    assert {widget["id"] for widget in response.data} >= {"traffic", "sources", "usage", "revenue"}


@pytest.mark.django_db
def test_dashboard_widget_public_and_template_flow(authenticated_client, organization):
    dashboard_response = authenticated_client.post(
        "/api/v1/dashboards/",
        {"name": "Public Dashboard", "visibility": "public", "refresh_interval": 30},
        format="json",
    )
    assert dashboard_response.status_code == 201
    dashboard_id = dashboard_response.data["id"]
    widget_response = authenticated_client.post(
        f"/api/v1/dashboards/{dashboard_id}/widgets/",
        {
            "type": "kpi",
            "title": "Sessions",
            "position": {"x": 0, "y": 0},
            "query_config": {"metric": "sessions", "range": "7d"},
            "chart_config": {},
        },
        format="json",
    )
    assert widget_response.status_code == 201
    data_response = authenticated_client.get(f"/api/v1/dashboards/{dashboard_id}/data/?range=7d")
    assert data_response.status_code == 200
    assert data_response.data["widgets"][0]["data"]["kpi"]["label"] == "Sessions"

    token = dashboard_response.data["public_token"]
    public_response = authenticated_client.get(f"/api/v1/public/dashboards/{token}/")
    assert public_response.status_code == 200
    assert public_response.data["id"] == dashboard_id

    template = DashboardTemplate.objects.create(
        name="Test Template",
        slug="test-template",
        widgets=[
            {"type": "kpi", "title": "Purchases", "position": {"x": 0, "y": 0}, "query_config": {"metric": "purchases"}}
        ],
    )
    instantiate = authenticated_client.post(f"/api/v1/dashboards/templates/{template.id}/instantiate/", {}, format="json")
    assert instantiate.status_code == 201
    assert Widget.objects.filter(dashboard_id=instantiate.data["id"], title="Purchases").exists()


@pytest.mark.django_db(transaction=True)
def test_event_creation_invalidates_dashboard_cache(organization):
    cache_key = f"overview:{organization.id}:7d"
    cache.set(cache_key, [{"id": "stale"}], 60)
    payload = EventPayload.model_validate(
        {
            "event_type": "pageview",
            "message": "/fresh",
            "timestamp": timezone.now().isoformat(),
            "properties": {"source": "Direct", "feature": "Dashboard Analytics"},
        }
    )
    create_event(organization=organization, payload=payload)
    assert cache.get(cache_key) is None


@pytest.mark.django_db
def test_alert_rule_crud(authenticated_client):
    response = authenticated_client.post(
        "/api/v1/alerts/rules/",
        {
            "name": "High Errors",
            "metric": "error_rate",
            "operator": ">",
            "threshold": 5,
            "duration": "10m",
            "status": "Active",
            "severity": "critical",
            "channels": ["in-app"],
        },
        format="json",
    )
    assert response.status_code == 201
    rule_id = response.data["id"]
    patch = authenticated_client.patch(f"/api/v1/alerts/rules/{rule_id}/", {"threshold": 10}, format="json")
    assert patch.status_code == 200
    assert patch.data["threshold"] == 10
    delete = authenticated_client.delete(f"/api/v1/alerts/rules/{rule_id}/")
    assert delete.status_code == 204
    assert not AlertRule.objects.filter(id=rule_id).exists()


@pytest.mark.django_db
def test_alert_evaluation_triggers_once_and_resolves(organization):
    rule = AlertRule.objects.create(
        organization=organization,
        name="High Errors",
        metric="error_rate",
        operator=">",
        threshold=50,
        duration_seconds=600,
        severity="critical",
        channels=["in-app"],
    )
    for event_type in ["pageview", "error", "error"]:
        Event.objects.create(
            organization=organization,
            event_type=event_type,
            timestamp=timezone.now(),
            message=event_type,
            properties={},
        )
    assert evaluate_alert_rules_for_org(str(organization.id)) == 1
    assert AlertHistory.objects.filter(alert_rule=rule, resolved_at__isnull=True).count() == 1
    assert evaluate_alert_rules_for_org(str(organization.id)) == 1
    assert AlertHistory.objects.filter(alert_rule=rule).count() == 1
    rule.refresh_from_db()
    rule.threshold = 100
    rule.save(update_fields=["threshold", "updated_at"])
    assert evaluate_alert_rules_for_org(str(organization.id)) == 0
    rule.refresh_from_db()
    assert rule.status == AlertRule.Status.ACTIVE
    assert AlertHistory.objects.get(alert_rule=rule).resolved_at is not None


@pytest.mark.django_db(transaction=True)
def test_muted_rule_does_not_trigger_and_delivery_is_recorded(organization):
    NotificationChannel.objects.create(organization=organization, type=NotificationChannel.Type.IN_APP, enabled=True, config={})
    rule = AlertRule.objects.create(
        organization=organization,
        name="Muted Errors",
        metric="sessions",
        operator=">",
        threshold=0,
        duration_seconds=600,
        severity="warning",
        channels=["in-app"],
        status=AlertRule.Status.MUTED,
        muted_until=timezone.now() + timedelta(minutes=30),
    )
    Event.objects.create(organization=organization, event_type="pageview", timestamp=timezone.now(), message="/", properties={})
    assert evaluate_alert_rules_for_org(str(organization.id)) == 0
    assert not AlertHistory.objects.filter(alert_rule=rule).exists()

    rule.status = AlertRule.Status.ACTIVE
    rule.muted_until = None
    rule.save(update_fields=["status", "muted_until", "updated_at"])
    assert evaluate_alert_rules_for_org(str(organization.id)) == 1
    history = AlertHistory.objects.get(alert_rule=rule)
    assert NotificationDelivery.objects.filter(alert_history=history, status="sent").exists()


@pytest.mark.django_db
def test_demo_event_endpoint_creates_backend_event(authenticated_client, organization):
    response = authenticated_client.post("/api/v1/demo/events/", {"type": "error"}, format="json")
    assert response.status_code == 201
    assert response.data["type"] == "error"
    assert Event.objects.filter(organization=organization, event_type="error").exists()


@pytest.mark.django_db
def test_seed_demo_command_is_idempotent():
    first_out = StringIO()
    call_command("seed_demo", stdout=first_out)
    first_user = get_user_model().objects.get(email="sarah.chen@nexus.io")
    first_org = Organization.objects.get(slug="nexus-analytics")
    first_event_count = Event.objects.filter(organization=first_org).count()
    second_out = StringIO()
    call_command("seed_demo", stdout=second_out)
    second_org = Organization.objects.get(slug="nexus-analytics")
    assert first_user.email == "sarah.chen@nexus.io"
    assert Event.objects.filter(organization=second_org).count() == first_event_count
    assert first_event_count >= 500
    assert "Demo API key:" in second_out.getvalue()


@pytest.mark.django_db(transaction=True)
def test_due_report_schedule_creates_report_run(authenticated_client, organization, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    dashboard = Dashboard.objects.create(organization=organization, name="Report Dashboard")
    Widget.objects.create(dashboard=dashboard, type=Widget.Type.KPI, title="Sessions", position={"x": 0, "y": 0}, query_config={"metric": "sessions"})
    schedule = ReportSchedule.objects.create(
        organization=organization,
        dashboard=dashboard,
        frequency=ReportSchedule.Frequency.DAILY,
        recipients=[],
        next_run_at=timezone.now() - timedelta(minutes=1),
        enabled=True,
    )
    assert process_due_report_schedules() == 1
    run = ReportRun.objects.get(schedule=schedule)
    assert run.status == "completed"
    assert run.file_url.endswith(".html")
    response = authenticated_client.get("/api/v1/reports/history/")
    assert response.status_code == 200
    assert response.data[0]["id"] == str(run.id)


@pytest.mark.django_db
def test_health_and_metrics_endpoints(api_client):
    assert api_client.get("/api/v1/health/").status_code == 200
    assert api_client.get("/api/v1/health/db/").status_code == 200
    assert api_client.get("/api/v1/health/redis/").status_code == 200
    metrics = api_client.get("/api/v1/metrics/")
    assert metrics.status_code == 200
    assert "events" in metrics.data


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_channels_event_websocket_receives_broadcast(user, organization):
    token = await database_sync_to_async(lambda: str(RefreshToken.for_user(user).access_token))()
    communicator = WebsocketCommunicator(application, f"/ws/events/?token={token}")
    connected, _ = await communicator.connect()
    assert connected
    channel_layer = get_channel_layer()
    await channel_layer.group_send(
        organization_group(organization.id, "events"),
        {
            "type": "broadcast.message",
            "message": {
                "type": "event.created",
                "payload": {
                    "id": "evt-1",
                    "timestamp": timezone.now().isoformat(),
                    "type": "pageview",
                    "userId": "usr-123",
                    "message": "/dashboard",
                    "metadata": {"ip": "127.0.0.1"},
                },
            },
        },
    )
    message = await communicator.receive_json_from(timeout=1)
    assert message["type"] == "event.created"
    assert message["payload"]["userId"] == "usr-123"
    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_channels_rejects_invalid_token_and_dashboard_receives_invalidation(user, organization):
    invalid = WebsocketCommunicator(application, "/ws/events/?token=bad-token")
    connected, _ = await invalid.connect()
    assert not connected

    token = await database_sync_to_async(lambda: str(RefreshToken.for_user(user).access_token))()
    dashboard_communicator = WebsocketCommunicator(application, f"/ws/dashboards/?token={token}")
    connected, _ = await dashboard_communicator.connect()
    assert connected
    channel_layer = get_channel_layer()
    await channel_layer.group_send(
        organization_group(organization.id, "dashboard"),
        {
            "type": "broadcast.message",
            "message": {"type": "dashboard.invalidate", "payload": {"organizationId": str(organization.id)}},
        },
    )
    message = await dashboard_communicator.receive_json_from(timeout=1)
    assert message["type"] == "dashboard.invalidate"
    await dashboard_communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_channels_alert_websocket_receives_trigger(user, organization):
    token = await database_sync_to_async(lambda: str(RefreshToken.for_user(user).access_token))()
    communicator = WebsocketCommunicator(application, f"/ws/alerts/?token={token}")
    connected, _ = await communicator.connect()
    assert connected
    channel_layer = get_channel_layer()
    await channel_layer.group_send(
        organization_group(organization.id, "alerts"),
        {
            "type": "broadcast.message",
            "message": {"type": "alert.triggered", "payload": {"id": "hist-1", "message": "Triggered"}},
        },
    )
    message = await communicator.receive_json_from(timeout=1)
    assert message["type"] == "alert.triggered"
    await communicator.disconnect()
