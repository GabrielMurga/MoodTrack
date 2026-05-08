"""Testes do User custom e dos profiles."""

from __future__ import annotations

import pytest
from django.db import IntegrityError

from apps.accounts.models import PatientProfile, PsychologistProfile, User
from tests.factories import (
    PatientProfileFactory,
    PsychologistProfileFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


class TestUserManager:
    def test_create_user_without_password_results_in_unusable_password(self):
        user = User.objects.create_user(email="oauth@example.com")
        assert not user.has_usable_password()

    def test_create_user_with_password_results_in_usable_password(self):
        user = User.objects.create_user(email="pass@example.com", password="s3cret")
        assert user.has_usable_password()
        assert user.check_password("s3cret")

    def test_create_superuser_with_password(self):
        user = User.objects.create_superuser(email="admin@example.com", password="adm1n")
        assert user.is_staff
        assert user.is_superuser
        assert user.check_password("adm1n")

    def test_create_user_requires_email(self):
        with pytest.raises(ValueError):
            User.objects.create_user(email="")


class TestUserProfileFlags:
    def test_user_without_profiles(self):
        user = UserFactory()
        assert user.is_psychologist is False
        assert user.is_patient is False

    def test_user_with_psychologist_profile(self):
        user = UserFactory()
        PsychologistProfileFactory(user=user)
        user.refresh_from_db()
        assert user.is_psychologist is True
        assert user.is_patient is False

    def test_user_with_both_profiles(self):
        """Caso central: psicóloga que também faz terapia."""
        user = UserFactory()
        PsychologistProfileFactory(user=user)
        PatientProfileFactory(user=user)
        user.refresh_from_db()
        assert user.is_psychologist is True
        assert user.is_patient is True


class TestProfileUniqueness:
    def test_one_psychologist_profile_per_user(self):
        psych = PsychologistProfileFactory()
        with pytest.raises(IntegrityError):
            PsychologistProfile.objects.create(user=psych.user, crp_number="X")

    def test_one_patient_profile_per_user(self):
        patient = PatientProfileFactory()
        with pytest.raises(IntegrityError):
            PatientProfile.objects.create(user=patient.user)
