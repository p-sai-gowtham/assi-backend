from __future__ import annotations

from rest_framework import serializers

from api_keys.models import OrganizationAPIKey


class OrganizationAPIKeySerializer(serializers.ModelSerializer):
    raw_key = serializers.CharField(read_only=True)

    class Meta:
        model = OrganizationAPIKey
        fields = ["id", "name", "prefix", "revoked_at", "last_used_at", "created_at", "raw_key"]
        read_only_fields = ["id", "prefix", "revoked_at", "last_used_at", "created_at", "raw_key"]
