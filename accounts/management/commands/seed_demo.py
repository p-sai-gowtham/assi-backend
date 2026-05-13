from __future__ import annotations

import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from accounts.models import UserPreference
from alerts.models import AlertHistory, AlertRule, NotificationChannel
from alerts.tasks import evaluate_alert_rules_for_org
from api_keys.models import OrganizationAPIKey
from billing.models import Invoice, Plan, Subscription, UsageCounter
from dashboards.models import Dashboard, DashboardTemplate, Widget
from ingestion.models import DataSource, Event
from organizations.models import Membership, Organization


class Command(BaseCommand):
    help = "Seed an idempotent demo tenant with realistic analytics data."

    def handle(self, *args, **options):
        random.seed(42)
        raw_key = self.seed()
        self.stdout.write(self.style.SUCCESS("Demo data seeded."))
        self.stdout.write("Demo login: sarah.chen@nexus.io / Password123!")
        self.stdout.write(f"Demo API key: {raw_key}")

    @transaction.atomic
    def seed(self) -> str:
        now = timezone.now()
        User = get_user_model()

        existing_org = Organization.objects.filter(slug="nexus-analytics").first()
        if existing_org:
            existing_org.delete()

        user, _ = User.objects.update_or_create(
            email="sarah.chen@nexus.io",
            defaults={"name": "Sarah Chen", "avatar": "/avatar-1.jpg", "is_active": True},
        )
        user.set_password("Password123!")
        user.save(update_fields=["password", "name", "avatar", "is_active"])

        organization = Organization.objects.create(name="Nexus Analytics", slug=slugify("Nexus Analytics"))
        Membership.objects.create(
            organization=organization,
            user=user,
            role=Membership.Role.OWNER,
            status=Membership.Status.ACTIVE,
        )
        UserPreference.objects.update_or_create(
            user=user,
            defaults={
                "theme": "dark",
                "language": "en",
                "timezone": "UTC",
                "email_notifications": True,
                "push_notifications": True,
                "slack_enabled": False,
                "webhook_enabled": False,
            },
        )

        api_key, raw_key = OrganizationAPIKey.create_with_raw_key(
            organization=organization,
            name="Demo Ingestion Key",
        )

        data_sources = {
            "api": DataSource.objects.create(
                organization=organization,
                type=DataSource.Type.API,
                name="API Ingestion",
                config={"description": "Server-side event ingestion"},
            ),
            "csv": DataSource.objects.create(
                organization=organization,
                type=DataSource.Type.CSV,
                name="CSV Upload",
                config={"description": "Bulk imported event files"},
            ),
            "webhook": DataSource.objects.create(
                organization=organization,
                type=DataSource.Type.WEBHOOK,
                name="Webhook Receiver",
                config={"description": "Partner webhook events"},
            ),
        }
        self.seed_dashboard_templates()

        events = self.build_events(organization, data_sources, now)
        Event.objects.bulk_create(events, batch_size=500)

        dashboard = Dashboard.objects.create(
            organization=organization,
            name="Main Analytics Overview",
            description="Core traffic, source, usage, and revenue metrics.",
        )
        widgets = [
            ("traffic", Widget.Type.LINE, "Traffic Overview", {"x": 0, "y": 0}),
            ("sources", Widget.Type.DOUGHNUT, "Traffic Sources", {"x": 1, "y": 0}),
            ("usage", Widget.Type.BAR, "Product Usage", {"x": 0, "y": 1}),
            ("revenue", Widget.Type.AREA, "Revenue", {"x": 1, "y": 1}),
        ]
        for metric, widget_type, title, position in widgets:
            Widget.objects.create(
                dashboard=dashboard,
                type=widget_type,
                title=title,
                position=position,
                query_config={"metric": metric, "range": "7d"},
                chart_config={},
            )

        NotificationChannel.objects.create(
            organization=organization,
            type=NotificationChannel.Type.IN_APP,
            enabled=True,
            config={},
        )
        NotificationChannel.objects.create(
            organization=organization,
            type=NotificationChannel.Type.EMAIL,
            enabled=True,
            config={"email": user.email},
        )
        NotificationChannel.objects.create(
            organization=organization,
            type=NotificationChannel.Type.WEBHOOK,
            enabled=False,
            config={},
        )

        rules = [
            ("High Error Rate", "error_rate", ">", 5, 600, "critical", ["in-app", "email"]),
            ("API Latency Spike", "api_latency", ">", 500, 600, "warning", ["in-app"]),
            ("Low Sessions", "sessions", "<", 5, 600, "warning", ["in-app"]),
            ("Revenue Spike", "revenue", ">", 500, 600, "info", ["in-app", "email"]),
        ]
        created_rules = []
        for name, metric, operator, threshold, duration, severity, channels in rules:
            created_rules.append(
                AlertRule.objects.create(
                    organization=organization,
                    name=name,
                    metric=metric,
                    operator=operator,
                    threshold=threshold,
                    duration_seconds=duration,
                    status=AlertRule.Status.ACTIVE,
                    severity=severity,
                    channels=channels,
                    enabled=True,
                )
            )

        for index, rule in enumerate(created_rules[:3]):
            triggered_at = now - timedelta(days=7 - index, hours=index)
            AlertHistory.objects.create(
                alert_rule=rule,
                triggered_at=triggered_at,
                resolved_at=triggered_at + timedelta(minutes=35 + index * 5),
                value=rule.threshold + 10 + index,
                message=f"{rule.name} was triggered during demo traffic.",
            )

        plan, _ = Plan.objects.update_or_create(
            name="Pro Plan",
            defaults={
                "price_monthly": 299,
                "price_annual": 2990,
                "features": {
                    "events": 100000,
                    "dashboards": 20,
                    "alerts": 25,
                    "team_members": 10,
                },
            },
        )
        Subscription.objects.create(
            organization=organization,
            plan=plan,
            status="active",
            billing_period="annual",
            current_period_start=(now - timedelta(days=65)).date(),
            current_period_end=(now + timedelta(days=300)).date(),
        )
        purchase_count = sum(1 for event in events if event.event_type == "purchase")
        api_call_count = sum(1 for event in events if event.event_type == "api_call")
        active_users = len({event.external_user_id for event in events if event.external_user_id})
        UsageCounter.objects.bulk_create(
            [
                UsageCounter(organization=organization, label="Monthly Events", used=len(events), limit=100000, unit="events", color="#3B82F6"),
                UsageCounter(organization=organization, label="API Calls", used=api_call_count, limit=50000, unit="calls", color="#06B6D4"),
                UsageCounter(organization=organization, label="Active Users", used=active_users, limit=10000, unit="users", color="#10B981"),
                UsageCounter(organization=organization, label="Reports Generated", used=18, limit=500, unit="reports", color="#F59E0B"),
            ]
        )
        for month_offset in range(4):
            invoice_date = (now - timedelta(days=30 * month_offset)).date()
            Invoice.objects.create(
                organization=organization,
                invoice_number=f"INV-DEMO-{invoice_date.strftime('%Y%m')}",
                date=invoice_date,
                amount=299,
                status="paid",
                plan_name=plan.name,
                file_url="",
            )

        transaction.on_commit(lambda: evaluate_alert_rules_for_org.delay(str(organization.id)))
        api_key.refresh_from_db()
        return raw_key

    def seed_dashboard_templates(self) -> None:
        templates = [
            (
                "Web Analytics",
                "web-analytics",
                "Traffic, source, conversion, and session analytics.",
                [
                    {"type": Widget.Type.LINE, "title": "Traffic Overview", "position": {"x": 0, "y": 0}, "query_config": {"metric": "traffic", "range": "7d"}},
                    {"type": Widget.Type.DOUGHNUT, "title": "Traffic Sources", "position": {"x": 1, "y": 0}, "query_config": {"metric": "sources", "range": "7d"}},
                    {"type": Widget.Type.KPI, "title": "New Users", "position": {"x": 0, "y": 1}, "query_config": {"metric": "new_users", "range": "7d"}},
                ],
            ),
            (
                "Sales",
                "sales",
                "Revenue, purchases, and customer activity.",
                [
                    {"type": Widget.Type.AREA, "title": "Revenue", "position": {"x": 0, "y": 0}, "query_config": {"metric": "revenue", "range": "30d"}},
                    {"type": Widget.Type.KPI, "title": "Purchases", "position": {"x": 1, "y": 0}, "query_config": {"metric": "purchases", "range": "30d"}},
                    {"type": Widget.Type.TABLE, "title": "Recent Transactions", "position": {"x": 0, "y": 1}, "query_config": {"metric": "purchase", "range": "30d"}},
                ],
            ),
            (
                "DevOps",
                "devops",
                "API reliability, latency, and error monitoring.",
                [
                    {"type": Widget.Type.KPI, "title": "Error Rate", "position": {"x": 0, "y": 0}, "query_config": {"metric": "error_rate", "range": "24h"}},
                    {"type": Widget.Type.KPI, "title": "API Latency", "position": {"x": 1, "y": 0}, "query_config": {"metric": "api_latency", "range": "24h"}},
                    {"type": Widget.Type.BAR, "title": "Exports", "position": {"x": 0, "y": 1}, "query_config": {"metric": "exports", "range": "7d"}},
                ],
            ),
        ]
        for name, slug, description, widgets in templates:
            DashboardTemplate.objects.update_or_create(
                slug=slug,
                defaults={"name": name, "description": description, "widgets": widgets, "is_active": True},
            )

    def build_events(self, organization: Organization, data_sources: dict[str, DataSource], now):
        sources = ["Google Search", "Direct", "Social Media", "Referral", "Email"]
        features = [
            "Dashboard Analytics",
            "Report Builder",
            "API Integration",
            "Alert Management",
            "Data Exports",
            "Team Collaboration",
        ]
        countries = ["US", "CA", "GB", "DE", "IN", "AU", "BR"]
        devices = ["desktop", "mobile", "tablet"]
        browsers = ["Chrome", "Safari", "Firefox", "Edge"]
        types = ["pageview", "login", "purchase", "signup", "api_call", "error", "export"]
        weights = [34, 14, 10, 8, 20, 8, 6]
        events = []
        for index in range(525):
            event_type = random.choices(types, weights=weights, k=1)[0]
            timestamp = now - timedelta(
                days=random.randint(0, 30),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59),
            )
            feature = random.choice(features)
            properties = {
                "source": random.choice(sources),
                "feature": feature,
                "country": random.choice(countries),
                "device": random.choice(devices),
                "browser": random.choice(browsers),
            }
            if event_type == "api_call":
                properties["latency_ms"] = random.choice([95, 140, 180, 260, 420, 650, 900])
            if event_type == "purchase":
                properties["amount"] = random.choice([29, 49, 99, 199, 299, 499])
                properties["status"] = "completed"
            if index % 80 == 0:
                properties["expense"] = True
                properties["amount"] = random.choice([12.5, 24, 49, 120])
            message = {
                "pageview": f"/{feature.lower().replace(' ', '-')}",
                "login": "User logged in",
                "purchase": "Pro Plan Subscription",
                "signup": "New user signup",
                "api_call": "POST /api/v1/query",
                "error": random.choice(["500 API error", "Dashboard render error", "Webhook timeout"]),
                "export": "CSV export completed",
            }[event_type]
            events.append(
                Event(
                    organization=organization,
                    data_source=random.choice(list(data_sources.values())),
                    event_type=event_type,
                    external_user_id=f"usr-demo-{random.randint(1, 180):03d}",
                    message=message,
                    timestamp=timestamp,
                    properties=properties,
                    ip_address=f"10.0.{random.randint(0, 12)}.{random.randint(1, 254)}",
                )
            )

        recent_for_alerts = [
            ("pageview", "/dashboard", {"source": "Google Search", "feature": "Dashboard Analytics"}),
            ("api_call", "POST /api/v1/query", {"source": "Direct", "feature": "API Integration", "latency_ms": 950}),
            ("purchase", "Enterprise upgrade", {"source": "Email", "feature": "Report Builder", "amount": 799, "status": "completed"}),
        ]
        recent_for_alerts.extend(
            [("error", "500 API error", {"source": "Direct", "feature": "API Integration"}) for _ in range(8)]
        )
        for offset, (event_type, message, properties) in enumerate(recent_for_alerts):
            base_properties = {
                "country": "US",
                "device": "desktop",
                "browser": "Chrome",
                **properties,
            }
            events.append(
                Event(
                    organization=organization,
                    data_source=data_sources["api"],
                    event_type=event_type,
                    external_user_id=f"usr-demo-recent-{offset:03d}",
                    message=message,
                    timestamp=now - timedelta(minutes=max(1, 9 - offset)),
                    properties=base_properties,
                    ip_address=f"10.1.1.{offset + 10}",
                )
            )
        return events
