from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from api_keys.models import OrganizationAPIKey
from organizations.models import Membership, Organization


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def organization():
    return Organization.objects.create(name="Test Org", slug="test-org")


@pytest.fixture
def user(organization):
    User = get_user_model()
    user = User.objects.create_user(email="owner@example.com", password="Password123!", name="Owner")
    Membership.objects.create(organization=organization, user=user, role=Membership.Role.OWNER)
    return user


@pytest.fixture
def authenticated_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def api_key(organization):
    return OrganizationAPIKey.create_with_raw_key(organization=organization, name="Test Key")
