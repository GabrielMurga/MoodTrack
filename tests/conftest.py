"""Pytest fixtures compartilhadas pelo projeto."""

import pytest
from django.test import Client


@pytest.fixture
def client() -> Client:
    return Client()
