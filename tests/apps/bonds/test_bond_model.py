"""Testes do Bond — state machine, geração de código, querysets."""

from __future__ import annotations

import pytest
from django.db import IntegrityError

from apps.bonds.models import (
    _INVITE_CODE_ALPHABET,
    Bond,
    BondStatus,
    InvalidBondTransition,
    generate_invite_code,
)
from tests.factories import (
    BondFactory,
    PatientProfileFactory,
    PsychologistProfileFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


class TestInviteCode:
    def test_default_length_is_8(self):
        code = generate_invite_code()
        assert len(code) == 8

    def test_uses_unambiguous_alphabet(self):
        code = generate_invite_code()
        for ch in code:
            assert ch in _INVITE_CODE_ALPHABET

    def test_no_collisions_in_1000_calls(self):
        codes = {generate_invite_code() for _ in range(1000)}
        assert len(codes) == 1000

    def test_bond_default_factory_generates_code(self):
        bond = BondFactory()
        assert len(bond.invite_code) == 8


class TestStateTransitions:
    def test_new_bond_starts_invited(self):
        bond = BondFactory()
        assert bond.status == BondStatus.INVITED
        assert bond.patient is None

    def test_accept_invite_sets_patient_and_pending(self):
        bond = BondFactory()
        patient = PatientProfileFactory()
        bond.accept_invite(patient)

        assert bond.status == BondStatus.PENDING_CONFIRMATION
        assert bond.patient == patient
        assert bond.patient_entered_at is not None

    def test_accept_invite_invalid_from_active(self):
        bond = BondFactory(active=True)
        patient = PatientProfileFactory()
        with pytest.raises(InvalidBondTransition):
            bond.accept_invite(patient)

    def test_confirm_only_from_pending(self):
        bond = BondFactory(pending=True)
        bond.confirm()
        assert bond.status == BondStatus.ACTIVE
        assert bond.psychologist_confirmed_at is not None

    def test_confirm_from_invited_fails(self):
        bond = BondFactory()
        with pytest.raises(InvalidBondTransition):
            bond.confirm()

    def test_end_from_any_alive_state(self):
        user = UserFactory()
        for trait in ["pending", "active"]:
            bond = BondFactory(**{trait: True})
            bond.end(by_user=user)
            assert bond.status == BondStatus.ENDED
            assert bond.ended_at is not None
            assert bond.ended_by == user

    def test_end_already_ended_fails(self):
        bond = BondFactory(ended=True)
        with pytest.raises(InvalidBondTransition):
            bond.end(by_user=UserFactory())

    def test_cannot_accept_own_invite_as_dual_user(self):
        """User dual (psicóloga + paciente) não pode usar próprio código de convite."""
        user = UserFactory()
        psych_profile = PsychologistProfileFactory(user=user)
        patient_profile = PatientProfileFactory(user=user)

        bond = BondFactory(psychologist=psych_profile)
        with pytest.raises(InvalidBondTransition, match="próprio código"):
            bond.accept_invite(patient_profile)

        bond.refresh_from_db()
        assert bond.status == BondStatus.INVITED
        assert bond.patient is None


class TestUniqueAliveBondConstraint:
    def test_cannot_have_two_alive_bonds_for_same_pair(self):
        psych = PsychologistProfileFactory()
        patient = PatientProfileFactory()
        Bond.objects.create(
            psychologist=psych, patient=patient, status=BondStatus.ACTIVE
        )
        with pytest.raises(IntegrityError):
            Bond.objects.create(
                psychologist=psych, patient=patient, status=BondStatus.PENDING_CONFIRMATION
            )

    def test_can_have_ended_bond_plus_new_alive_bond(self):
        psych = PsychologistProfileFactory()
        patient = PatientProfileFactory()
        Bond.objects.create(
            psychologist=psych, patient=patient, status=BondStatus.ENDED
        )
        # Não deve falhar — ENDED não conta para a constraint.
        Bond.objects.create(
            psychologist=psych, patient=patient, status=BondStatus.ACTIVE
        )


class TestQuerysetIsolation:
    def test_for_psychologist_filters_to_owner(self):
        psych_a = PsychologistProfileFactory()
        psych_b = PsychologistProfileFactory()
        BondFactory(psychologist=psych_a)
        BondFactory(psychologist=psych_b)

        bonds_a = Bond.objects.for_psychologist(psych_a)
        assert bonds_a.count() == 1
        assert bonds_a.first().psychologist == psych_a

    def test_for_user_returns_empty_for_user_without_profile(self):
        """Fail-closed: user sem perfil vê queryset vazio, não erro."""
        BondFactory()  # bond no DB
        user = UserFactory()
        assert Bond.objects.for_user(user).count() == 0

    def test_for_user_returns_bonds_from_both_profiles(self):
        """User dual (psicóloga + paciente) vê bonds dos dois lados."""
        user = UserFactory()
        psych_profile = PsychologistProfileFactory(user=user)
        patient_profile = PatientProfileFactory(user=user)

        BondFactory(psychologist=psych_profile)  # como psicóloga
        BondFactory(active=True, patient=patient_profile)  # como paciente
        BondFactory()  # de outro psicólogo, não deve aparecer

        user.refresh_from_db()
        assert Bond.objects.for_user(user).count() == 2

    def test_active_returns_only_active(self):
        BondFactory()  # invited
        BondFactory(pending=True)
        BondFactory(active=True)
        BondFactory(ended=True)

        assert Bond.objects.active().count() == 1
        assert Bond.objects.alive().count() == 3
