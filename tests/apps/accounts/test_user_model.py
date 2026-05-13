"""Testes do User custom e dos profiles."""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.accounts.models import HealthcareProvider, PatientProfile, ProviderKind, User
from tests.factories import (
    HealthcareProviderFactory,
    PatientProfileFactory,
    PsychiatristProviderFactory,
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
        assert user.is_provider is False
        assert user.is_psychologist is False
        assert user.is_psychiatrist is False
        assert user.is_patient is False

    def test_user_with_provider_profile_psychologist(self):
        user = UserFactory()
        HealthcareProviderFactory(user=user)
        user.refresh_from_db()
        assert user.is_provider is True
        assert user.is_psychologist is True
        assert user.is_psychiatrist is False
        assert user.is_patient is False

    def test_user_with_psychiatrist_profile(self):
        user = UserFactory()
        PsychiatristProviderFactory(user=user)
        user.refresh_from_db()
        assert user.is_provider is True
        assert user.is_psychologist is False
        assert user.is_psychiatrist is True

    def test_user_with_both_profiles(self):
        """Caso central: profissional que também faz terapia."""
        user = UserFactory()
        HealthcareProviderFactory(user=user)
        PatientProfileFactory(user=user)
        user.refresh_from_db()
        assert user.is_provider is True
        assert user.is_patient is True


class TestProfileUniqueness:
    def test_one_provider_profile_per_user(self):
        provider = HealthcareProviderFactory()
        with pytest.raises(IntegrityError):
            HealthcareProvider.objects.create(
                user=provider.user,
                kind=ProviderKind.PSYCHOLOGIST,
                crp_number="X",
            )

    def test_one_patient_profile_per_user(self):
        patient = PatientProfileFactory()
        with pytest.raises(IntegrityError):
            PatientProfile.objects.create(user=patient.user)


class TestProviderKindValidation:
    def test_psychologist_cannot_have_crm(self):
        provider = HealthcareProviderFactory.build(
            kind=ProviderKind.PSYCHOLOGIST,
            crp_number="06/12345",
            crm_number="SP/9999",
        )
        with pytest.raises(ValidationError):
            provider.full_clean()

    def test_psychiatrist_cannot_have_crp(self):
        provider = HealthcareProviderFactory.build(
            kind=ProviderKind.PSYCHIATRIST,
            crp_number="06/12345",
            crm_number="SP/9999",
        )
        with pytest.raises(ValidationError):
            provider.full_clean()

    def test_check_constraint_blocks_psychologist_with_crm_at_db_level(self):
        user = UserFactory()
        with pytest.raises(IntegrityError):
            HealthcareProvider.objects.create(
                user=user,
                kind=ProviderKind.PSYCHOLOGIST,
                crp_number="06/12345",
                crm_number="SP/9999",
            )

    def test_can_prescribe_only_for_psychiatrist(self):
        psychologist = HealthcareProviderFactory()
        psychiatrist = PsychiatristProviderFactory()
        assert psychologist.can_prescribe is False
        assert psychiatrist.can_prescribe is True
