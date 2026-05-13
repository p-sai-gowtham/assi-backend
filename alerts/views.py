from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from alerts.models import AlertHistory, AlertRule
from alerts.serializers import AlertHistorySerializer, AlertRuleSerializer
from common.realtime import broadcast, organization_group
from common.permissions import CanManageAlerts, IsOrgMember, ReadAnyWriteAnalyst
from common.tenancy import ensure_request_organization


def broadcast_rule(rule: AlertRule, message_type: str = "alert.rule.updated") -> None:
    broadcast(
        organization_group(rule.organization_id, "alerts"),
        {"type": message_type, "payload": AlertRuleSerializer(rule).data},
    )


class AlertRuleListCreateView(APIView):
    permission_classes = [ReadAnyWriteAnalyst]

    def get(self, request):
        organization = ensure_request_organization(request)
        rules = AlertRule.objects.filter(organization=organization).order_by("-created_at")
        return Response(AlertRuleSerializer(rules, many=True).data)

    def post(self, request):
        organization = ensure_request_organization(request)
        serializer = AlertRuleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rule = serializer.save(organization=organization)
        broadcast_rule(rule)
        return Response(AlertRuleSerializer(rule).data, status=status.HTTP_201_CREATED)


class AlertRuleDetailView(APIView):
    permission_classes = [ReadAnyWriteAnalyst]

    def get_object(self, request, pk):
        organization = ensure_request_organization(request)
        return get_object_or_404(AlertRule, pk=pk, organization=organization)

    def patch(self, request, pk):
        rule = self.get_object(request, pk)
        serializer = AlertRuleSerializer(rule, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        broadcast_rule(rule)
        return Response(AlertRuleSerializer(rule).data)

    def delete(self, request, pk):
        rule = self.get_object(request, pk)
        rule_id = str(rule.id)
        organization_id = rule.organization_id
        rule.delete()
        broadcast(
            organization_group(organization_id, "alerts"),
            {"type": "alert.rule.deleted", "payload": {"id": rule_id}},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class AlertRuleMuteView(APIView):
    permission_classes = [CanManageAlerts]

    def post(self, request, pk):
        organization = ensure_request_organization(request)
        rule = get_object_or_404(AlertRule, pk=pk, organization=organization)
        rule.status = AlertRule.Status.MUTED
        muted_until = request.data.get("muted_until") or request.data.get("mutedUntil")
        if muted_until:
            rule.muted_until = parse_datetime(muted_until) if isinstance(muted_until, str) else muted_until
        rule.save(update_fields=["status", "muted_until", "updated_at"])
        broadcast_rule(rule)
        return Response(AlertRuleSerializer(rule).data)


class AlertRuleResolveView(APIView):
    permission_classes = [CanManageAlerts]

    def post(self, request, pk):
        organization = ensure_request_organization(request)
        rule = get_object_or_404(AlertRule, pk=pk, organization=organization)
        rule.status = AlertRule.Status.RESOLVED
        rule.save(update_fields=["status", "updated_at"])
        now = timezone.now()
        histories = list(AlertHistory.objects.filter(alert_rule=rule, resolved_at__isnull=True))
        for history in histories:
            history.resolved_at = now
            history.save(update_fields=["resolved_at", "updated_at"])
            broadcast(
                organization_group(rule.organization_id, "alerts"),
                {"type": "alert.resolved", "payload": AlertHistorySerializer(history).data},
            )
        broadcast_rule(rule)
        return Response(AlertRuleSerializer(rule).data)


class AlertRuleReactivateView(APIView):
    permission_classes = [CanManageAlerts]

    def post(self, request, pk):
        organization = ensure_request_organization(request)
        rule = get_object_or_404(AlertRule, pk=pk, organization=organization)
        rule.status = AlertRule.Status.ACTIVE
        rule.enabled = True
        rule.muted_until = None
        rule.save(update_fields=["status", "enabled", "muted_until", "updated_at"])
        broadcast_rule(rule)
        return Response(AlertRuleSerializer(rule).data)


class AlertHistoryView(APIView):
    permission_classes = [IsOrgMember]

    def get(self, request):
        organization = ensure_request_organization(request)
        history = AlertHistory.objects.filter(alert_rule__organization=organization).select_related("alert_rule")[:100]
        return Response(AlertHistorySerializer(history, many=True).data)
