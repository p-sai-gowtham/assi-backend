from __future__ import annotations

from django.urls import re_path

from realtime.consumers import AlertConsumer, DashboardConsumer, EventConsumer

websocket_urlpatterns = [
    re_path(r"^ws/events/$", EventConsumer.as_asgi()),
    re_path(r"^ws/alerts/$", AlertConsumer.as_asgi()),
    re_path(r"^ws/dashboards/$", DashboardConsumer.as_asgi()),
    re_path(r"^ws/dashboards/(?P<dashboard_id>[^/]+)/$", DashboardConsumer.as_asgi()),
]
