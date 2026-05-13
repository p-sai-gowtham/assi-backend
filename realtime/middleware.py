from __future__ import annotations

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import User
from organizations.models import Membership


@database_sync_to_async
def get_user_and_membership(token: str):
    try:
        access = AccessToken(token)
        user = User.objects.get(id=access["user_id"], is_active=True)
        membership = Membership.objects.select_related("organization").filter(user=user, status="active").first()
        return user, membership
    except (TokenError, User.DoesNotExist, KeyError):
        return AnonymousUser(), None


class JWTAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        token = (query.get("token") or [""])[0]
        user, membership = await get_user_and_membership(token)
        scope["user"] = user
        scope["membership"] = membership
        scope["organization"] = membership.organization if membership else None
        return await self.inner(scope, receive, send)
