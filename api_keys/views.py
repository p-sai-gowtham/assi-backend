from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from api_keys.models import OrganizationAPIKey
from api_keys.serializers import OrganizationAPIKeySerializer
from common.permissions import CanManageAPIKeys
from common.tenancy import ensure_request_organization


class APIKeyListCreateView(APIView):
    permission_classes = [CanManageAPIKeys]

    def get(self, request):
        organization = ensure_request_organization(request)
        queryset = organization.api_keys.order_by("-created_at")
        return Response(OrganizationAPIKeySerializer(queryset, many=True).data)

    def post(self, request):
        organization = ensure_request_organization(request)
        serializer = OrganizationAPIKeySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        api_key, raw_key = OrganizationAPIKey.create_with_raw_key(
            organization=organization,
            name=serializer.validated_data["name"],
        )
        data = OrganizationAPIKeySerializer(api_key).data
        data["raw_key"] = raw_key
        return Response(data, status=status.HTTP_201_CREATED)


class APIKeyRotateView(APIView):
    permission_classes = [CanManageAPIKeys]

    def post(self, request, pk):
        organization = ensure_request_organization(request)
        api_key = get_object_or_404(OrganizationAPIKey, pk=pk, organization=organization)
        raw_key = api_key.rotate()
        data = OrganizationAPIKeySerializer(api_key).data
        data["raw_key"] = raw_key
        return Response(data)


class APIKeyRevokeView(APIView):
    permission_classes = [CanManageAPIKeys]

    def post(self, request, pk):
        organization = ensure_request_organization(request)
        api_key = get_object_or_404(OrganizationAPIKey, pk=pk, organization=organization)
        api_key.revoke()
        return Response(OrganizationAPIKeySerializer(api_key).data)
