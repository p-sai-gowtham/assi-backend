from __future__ import annotations

from rest_framework.throttling import ScopedRateThrottle


class APIKeyScopedRateThrottle(ScopedRateThrottle):
    def get_cache_key(self, request, view):
        scope = getattr(view, "throttle_scope", None)
        if scope not in {"ingestion_single", "ingestion_batch", "ingestion_csv"}:
            return None

        api_key = getattr(request, "auth", None)
        ident = getattr(api_key, "prefix", None) or self.get_ident(request)
        self.scope = scope
        self.rate = self.get_rate()
        self.num_requests, self.duration = self.parse_rate(self.rate)
        return self.cache_format % {"scope": self.scope, "ident": ident}
