from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

EventType = Literal["pageview", "login", "purchase", "signup", "api_call", "error", "export"]


class EventPayload(BaseModel):
    type: EventType = Field(alias="event_type")
    user_id: str = Field(default="", alias="external_user_id")
    message: str = ""
    timestamp: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, alias="properties")
    ip: str | None = Field(default=None, alias="ip_address")

    model_config = {
        "populate_by_name": True,
        "extra": "allow",
    }

    @model_validator(mode="before")
    @classmethod
    def normalize_frontend_aliases(cls, data):
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        if "event_type" not in normalized and "type" in normalized:
            normalized["event_type"] = normalized["type"]
        if "external_user_id" not in normalized:
            normalized["external_user_id"] = normalized.get("userId") or normalized.get("user_id") or ""
        if "properties" not in normalized and "metadata" in normalized:
            normalized["properties"] = normalized["metadata"]
        if "ip_address" not in normalized and "ip" in normalized:
            normalized["ip_address"] = normalized["ip"]
        normalized.setdefault("timestamp", datetime.now(timezone.utc))
        return normalized

    @field_validator("timestamp", mode="after")
    @classmethod
    def default_timestamp(cls, value: datetime | None) -> datetime:
        return value or datetime.now(timezone.utc)


class BatchEventPayload(BaseModel):
    events: list[EventPayload]

    @field_validator("events")
    @classmethod
    def validate_size(cls, value: list[EventPayload]) -> list[EventPayload]:
        if not value:
            raise ValueError("Batch must contain at least one event.")
        if len(value) > 500:
            raise ValueError("Batch cannot exceed 500 events.")
        return value
