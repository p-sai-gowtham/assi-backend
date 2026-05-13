from __future__ import annotations

from django.urls import path

from api_keys.views import APIKeyListCreateView, APIKeyRevokeView, APIKeyRotateView

urlpatterns = [
    path("", APIKeyListCreateView.as_view(), name="api-key-list-create"),
    path("<uuid:pk>/rotate/", APIKeyRotateView.as_view(), name="api-key-rotate"),
    path("<uuid:pk>/revoke/", APIKeyRevokeView.as_view(), name="api-key-revoke"),
]
