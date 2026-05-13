from __future__ import annotations

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from common.realtime import dashboard_group, organization_group
from dashboards.models import Dashboard


class OrgConsumer(AsyncJsonWebsocketConsumer):
    stream = ""

    async def connect(self):
        self.organization = self.scope.get("organization")
        if self.organization is None:
            await self.close(code=4401)
            return
        self.group_name = organization_group(self.organization.id, self.stream)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def broadcast_message(self, event):
        await self.send_json(event["message"])


class EventConsumer(OrgConsumer):
    stream = "events"


class AlertConsumer(OrgConsumer):
    stream = "alerts"


@database_sync_to_async
def dashboard_belongs_to_org(dashboard_id: str, organization_id: str) -> bool:
    return Dashboard.objects.filter(id=dashboard_id, organization_id=organization_id).exists()


class DashboardConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.organization = self.scope.get("organization")
        self.dashboard_id = self.scope["url_route"]["kwargs"].get("dashboard_id")
        if self.organization is None:
            await self.close(code=4401)
            return
        if self.dashboard_id is None:
            self.group_name = organization_group(self.organization.id, "dashboard")
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            return
        if not await dashboard_belongs_to_org(self.dashboard_id, str(self.organization.id)):
            await self.close(code=4403)
            return
        self.group_name = dashboard_group(self.organization.id, self.dashboard_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def broadcast_message(self, event):
        await self.send_json(event["message"])
