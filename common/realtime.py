from __future__ import annotations

from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def organization_group(organization_id: Any, stream: str) -> str:
    return f"org_{organization_id}_{stream}"


def dashboard_group(organization_id: Any, dashboard_id: Any) -> str:
    return f"org_{organization_id}_dashboard_{dashboard_id}"


def broadcast(group: str, message: dict[str, Any]) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    async_to_sync(channel_layer.group_send)(
        group,
        {"type": "broadcast.message", "message": message},
    )
