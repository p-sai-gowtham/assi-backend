from __future__ import annotations

import secrets

from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils import timezone

from common.models import UUIDTimestampModel
from organizations.models import Organization


class OrganizationAPIKey(UUIDTimestampModel):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="api_keys")
    name = models.CharField(max_length=255)
    prefix = models.CharField(max_length=16, db_index=True)
    hashed_key = models.CharField(max_length=255)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["organization", "revoked_at"])]

    @staticmethod
    def generate_raw_key() -> str:
        return f"na_live_{secrets.token_urlsafe(32)}"

    @staticmethod
    def extract_prefix(raw_key: str) -> str:
        return raw_key[:12]

    @classmethod
    def create_with_raw_key(cls, *, organization: Organization, name: str):
        raw_key = cls.generate_raw_key()
        api_key = cls.objects.create(
            organization=organization,
            name=name,
            prefix=cls.extract_prefix(raw_key),
            hashed_key=make_password(raw_key),
        )
        return api_key, raw_key

    def rotate(self):
        raw_key = self.generate_raw_key()
        self.prefix = self.extract_prefix(raw_key)
        self.hashed_key = make_password(raw_key)
        self.revoked_at = None
        self.save(update_fields=["prefix", "hashed_key", "revoked_at", "updated_at"])
        return raw_key

    def revoke(self) -> None:
        self.revoked_at = timezone.now()
        self.save(update_fields=["revoked_at", "updated_at"])

    def verify(self, raw_key: str) -> bool:
        return check_password(raw_key, self.hashed_key)

    def __str__(self) -> str:
        return f"{self.name} ({self.prefix})"
