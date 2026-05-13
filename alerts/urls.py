from __future__ import annotations

from django.urls import path

from alerts.views import (
    AlertHistoryView,
    AlertRuleDetailView,
    AlertRuleListCreateView,
    AlertRuleMuteView,
    AlertRuleReactivateView,
    AlertRuleResolveView,
)

urlpatterns = [
    path("rules/", AlertRuleListCreateView.as_view(), name="alert-rule-list-create"),
    path("rules/<uuid:pk>/", AlertRuleDetailView.as_view(), name="alert-rule-detail"),
    path("rules/<uuid:pk>/mute/", AlertRuleMuteView.as_view(), name="alert-rule-mute"),
    path("rules/<uuid:pk>/resolve/", AlertRuleResolveView.as_view(), name="alert-rule-resolve"),
    path("rules/<uuid:pk>/reactivate/", AlertRuleReactivateView.as_view(), name="alert-rule-reactivate"),
    path("history/", AlertHistoryView.as_view(), name="alert-history"),
]
