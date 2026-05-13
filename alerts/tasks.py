from __future__ import annotations

import json
import logging
import operator
from datetime import timedelta
from urllib import request as urllib_request
from urllib.error import URLError

from celery import shared_task
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from alerts.models import AlertHistory, AlertRule, NotificationChannel, NotificationDelivery
from alerts.serializers import AlertHistorySerializer, AlertRuleSerializer
from common.realtime import broadcast, organization_group
from ingestion.models import Event
from organizations.models import Organization

logger = logging.getLogger(__name__)

OPERATORS = {
    ">": operator.gt,
    "<": operator.lt,
    "==": operator.eq,
    ">=": operator.ge,
    "<=": operator.le,
}

CHANNEL_ALIASES = {
    "in-app": NotificationChannel.Type.IN_APP,
    "in_app": NotificationChannel.Type.IN_APP,
    "email": NotificationChannel.Type.EMAIL,
    "webhook": NotificationChannel.Type.WEBHOOK,
}


def metric_value(rule: AlertRule) -> float:
    since = timezone.now() - timedelta(seconds=rule.duration_seconds)
    events = Event.objects.filter(organization=rule.organization, timestamp__gte=since)
    if rule.metric == "error_rate":
        total = events.count()
        if total == 0:
            return 0
        return round((events.filter(event_type="error").count() / total) * 100, 2)
    if rule.metric == "sessions":
        return float(events.filter(event_type="pageview").count())
    if rule.metric == "revenue":
        return sum(float(event.properties.get("amount", 0) or 0) for event in events.filter(event_type="purchase"))
    if rule.metric == "api_latency":
        values = [float(event.properties.get("latency_ms", 0) or 0) for event in events.filter(event_type="api_call")]
        return max(values) if values else 0
    if rule.metric == "new_users":
        return float(events.filter(event_type="signup").count())
    if rule.metric == "purchases":
        return float(events.filter(event_type="purchase").count())
    if rule.metric == "exports":
        return float(events.filter(event_type="export").count())
    return float(events.filter(event_type=rule.metric).count())


def condition_matches(rule: AlertRule, value: float) -> bool:
    return OPERATORS[rule.operator](value, rule.threshold)


def is_muted(rule: AlertRule) -> bool:
    if rule.status != AlertRule.Status.MUTED:
        return False
    if rule.muted_until and rule.muted_until <= timezone.now():
        rule.status = AlertRule.Status.ACTIVE
        rule.muted_until = None
        rule.save(update_fields=["status", "muted_until", "updated_at"])
        return False
    return True


def enabled_channels(rule: AlertRule):
    configured = {CHANNEL_ALIASES.get(channel, channel) for channel in (rule.channels or [])}
    if not configured:
        configured = {NotificationChannel.Type.IN_APP}
    return NotificationChannel.objects.filter(
        organization=rule.organization,
        type__in=configured,
        enabled=True,
    )


def deliver_notification(history: AlertHistory) -> None:
    payload = AlertHistorySerializer(history).data
    for channel in enabled_channels(history.alert_rule):
        delivery = NotificationDelivery.objects.create(channel=channel, alert_history=history, status="queued")
        try:
            if channel.type == NotificationChannel.Type.EMAIL:
                recipient = channel.config.get("email") or channel.config.get("recipient")
                if recipient:
                    send_mail(
                        subject=f"Alert triggered: {history.alert_rule.name}",
                        message=history.message,
                        from_email=channel.config.get("from_email", "alerts@nexus.local"),
                        recipient_list=[recipient],
                        fail_silently=False,
                    )
                delivery.status = "sent"
            elif channel.type == NotificationChannel.Type.WEBHOOK:
                webhook_url = channel.config.get("url")
                if not webhook_url:
                    delivery.status = "skipped"
                    delivery.response_body = "Webhook URL is not configured."
                else:
                    body = json.dumps(payload).encode("utf-8")
                    req = urllib_request.Request(
                        webhook_url,
                        data=body,
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urllib_request.urlopen(req, timeout=5) as response:
                        delivery.status = "sent"
                        delivery.response_body = response.read(512).decode("utf-8", errors="ignore")
            else:
                delivery.status = "sent"
        except (Exception, URLError) as exc:
            logger.exception("Alert delivery failed for channel %s", channel.id)
            delivery.status = "failed"
            delivery.response_body = str(exc)
        delivery.save(update_fields=["status", "response_body", "updated_at"])

    broadcast(
        organization_group(history.alert_rule.organization_id, "alerts"),
        {"type": "notification.created", "payload": payload},
    )


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def deliver_notification_task(self, history_id: str) -> None:
    history = AlertHistory.objects.select_related("alert_rule", "alert_rule__organization").get(id=history_id)
    deliver_notification(history)


def broadcast_rule(rule: AlertRule, message_type: str) -> None:
    broadcast(
        organization_group(rule.organization_id, "alerts"),
        {"type": message_type, "payload": AlertRuleSerializer(rule).data},
    )


@transaction.atomic
def trigger_rule(rule: AlertRule, value: float) -> AlertHistory:
    open_history = AlertHistory.objects.select_for_update().filter(
        alert_rule=rule,
        resolved_at__isnull=True,
    ).first()
    if open_history:
        rule.status = AlertRule.Status.TRIGGERED
        rule.last_evaluated_at = timezone.now()
        rule.save(update_fields=["status", "last_evaluated_at", "updated_at"])
        return open_history

    history = AlertHistory.objects.create(
        alert_rule=rule,
        triggered_at=timezone.now(),
        value=value,
        message=f"{rule.name}: {rule.metric} {rule.operator} {rule.threshold} for {rule.duration_seconds}s (value {value})",
    )
    rule.status = AlertRule.Status.TRIGGERED
    rule.last_triggered = history.triggered_at
    rule.last_evaluated_at = history.triggered_at
    rule.save(update_fields=["status", "last_triggered", "last_evaluated_at", "updated_at"])
    transaction.on_commit(lambda: deliver_notification_task.delay(str(history.id)))
    transaction.on_commit(lambda: broadcast_rule(rule, "alert.rule.updated"))
    transaction.on_commit(
        lambda: broadcast(
            organization_group(rule.organization_id, "alerts"),
            {"type": "alert.triggered", "payload": AlertHistorySerializer(history).data},
        )
    )
    return history


@transaction.atomic
def resolve_rule(rule: AlertRule, value: float) -> AlertHistory | None:
    history = AlertHistory.objects.select_for_update().filter(
        alert_rule=rule,
        resolved_at__isnull=True,
    ).first()
    now = timezone.now()
    if history is None:
        rule.status = AlertRule.Status.ACTIVE
        rule.last_evaluated_at = now
        rule.save(update_fields=["status", "last_evaluated_at", "updated_at"])
        transaction.on_commit(lambda: broadcast_rule(rule, "alert.rule.updated"))
        return None

    history.resolved_at = now
    history.value = value
    history.save(update_fields=["resolved_at", "value", "updated_at"])
    rule.status = AlertRule.Status.ACTIVE
    rule.last_evaluated_at = now
    rule.save(update_fields=["status", "last_evaluated_at", "updated_at"])
    transaction.on_commit(lambda: broadcast_rule(rule, "alert.rule.updated"))
    transaction.on_commit(
        lambda: broadcast(
            organization_group(rule.organization_id, "alerts"),
            {"type": "alert.resolved", "payload": AlertHistorySerializer(history).data},
        )
    )
    return history


def evaluate_rule(rule: AlertRule) -> bool:
    if not rule.enabled or is_muted(rule):
        return False
    value = metric_value(rule)
    matched = condition_matches(rule, value)
    if matched:
        trigger_rule(rule, value)
        return True
    if rule.status == AlertRule.Status.TRIGGERED:
        resolve_rule(rule, value)
    else:
        rule.last_evaluated_at = timezone.now()
        rule.save(update_fields=["last_evaluated_at", "updated_at"])
    return False


@shared_task
def evaluate_alert_rules_for_org(org_id: str) -> int:
    organization = Organization.objects.get(id=org_id)
    triggered = 0
    rules = AlertRule.objects.select_related("organization").filter(
        organization=organization,
        enabled=True,
    ).exclude(status=AlertRule.Status.RESOLVED)
    for rule in rules:
        try:
            if evaluate_rule(rule):
                triggered += 1
        except Exception:
            logger.exception("Failed to evaluate alert rule %s", rule.id)
    return triggered


@shared_task
def evaluate_alert_rules() -> int:
    triggered = 0
    organization_ids = AlertRule.objects.filter(enabled=True).values_list("organization_id", flat=True).distinct()
    for org_id in organization_ids:
        triggered += evaluate_alert_rules_for_org(str(org_id))
    return triggered
