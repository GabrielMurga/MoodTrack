"""Testes do audit log — append-only enforcement e helper log_event."""

from __future__ import annotations

import pytest

from apps.audit.models import AuditLog, AuditLogError, log_event
from tests.factories import BondFactory, UserFactory

pytestmark = pytest.mark.django_db


class TestAuditLogAppendOnly:
    def test_create_works(self):
        user = UserFactory()
        entry = AuditLog.objects.create(actor=user, action="test.event")
        assert entry.pk is not None
        assert AuditLog.objects.count() == 1

    def test_save_after_create_raises(self):
        user = UserFactory()
        entry = AuditLog.objects.create(actor=user, action="test.event")
        entry.action = "tampered"
        with pytest.raises(AuditLogError, match="UPDATE"):
            entry.save()

    def test_delete_raises(self):
        user = UserFactory()
        entry = AuditLog.objects.create(actor=user, action="test.event")
        with pytest.raises(AuditLogError, match="DELETE"):
            entry.delete()


class TestLogEventHelper:
    def test_log_event_with_target(self):
        bond = BondFactory()
        user = UserFactory()
        entry = log_event(actor=user, action="bond.test", target=bond, code="X")

        assert entry.actor == user
        assert entry.action == "bond.test"
        assert entry.target_type == "Bond"
        assert entry.target_id == bond.pk
        assert entry.metadata == {"code": "X"}

    def test_log_event_without_target(self):
        user = UserFactory()
        entry = log_event(actor=user, action="login.success")

        assert entry.target_type == ""
        assert entry.target_id is None
        assert entry.metadata == {}

    def test_log_event_with_system_actor(self):
        """actor=None permitido para ações de sistema."""
        entry = log_event(actor=None, action="cron.cleanup")
        assert entry.actor is None
        assert entry.action == "cron.cleanup"
