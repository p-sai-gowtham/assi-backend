from __future__ import annotations

from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from api_keys.models import OrganizationAPIKey


class APIKeyAuthentication(BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        raw_key = request.headers.get("X-API-Key")
        auth_header = request.headers.get("Authorization", "")
        if not raw_key and auth_header.startswith(f"{self.keyword} "):
            raw_key = auth_header.removeprefix(f"{self.keyword} ").strip()
        if not raw_key:
            return None

        prefix = OrganizationAPIKey.extract_prefix(raw_key)
        candidates = OrganizationAPIKey.objects.select_related("organization").filter(
            prefix=prefix,
            revoked_at__isnull=True,
        )
        for api_key in candidates:
            if api_key.verify(raw_key):
                OrganizationAPIKey.objects.filter(pk=api_key.pk).update(last_used_at=timezone.now())
                return AnonymousUser(), api_key
        raise AuthenticationFailed("Invalid API key.")
