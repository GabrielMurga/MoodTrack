"""Factories para testes — uso de factory-boy.

CLAUDE.md: usar factory-boy para fixtures, não dados hardcoded.
"""

from __future__ import annotations

import datetime

import factory
from factory.django import DjangoModelFactory

from apps.accounts.models import PatientProfile, PsychologistProfile, User
from apps.bonds.models import Bond, BondStatus
from apps.journal.models import (
    ClinicalNote,
    JournalEntry,
    JournalEntryKind,
    MoodLevel,
    MoodLog,
)


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("email",)

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    full_name = factory.Faker("name", locale="pt_BR")
    is_active = True


class PsychologistProfileFactory(DjangoModelFactory):
    class Meta:
        model = PsychologistProfile

    user = factory.SubFactory(UserFactory)
    crp_number = factory.Sequence(lambda n: f"06/{10000 + n:05d}")
    bio = ""


class PatientProfileFactory(DjangoModelFactory):
    class Meta:
        model = PatientProfile

    user = factory.SubFactory(UserFactory)
    preferred_name = factory.Faker("first_name", locale="pt_BR")


class BondFactory(DjangoModelFactory):
    class Meta:
        model = Bond

    psychologist = factory.SubFactory(PsychologistProfileFactory)
    patient = None
    status = BondStatus.INVITED

    class Params:
        # Traits para criar bonds em estados específicos.
        pending = factory.Trait(
            patient=factory.SubFactory(PatientProfileFactory),
            status=BondStatus.PENDING_CONFIRMATION,
            patient_entered_at=factory.Faker("date_time_this_month", tzinfo=datetime.UTC),
        )
        active = factory.Trait(
            patient=factory.SubFactory(PatientProfileFactory),
            status=BondStatus.ACTIVE,
            patient_entered_at=factory.Faker("date_time_this_month", tzinfo=datetime.UTC),
            psychologist_confirmed_at=factory.Faker("date_time_this_month", tzinfo=datetime.UTC),
        )
        ended = factory.Trait(
            patient=factory.SubFactory(PatientProfileFactory),
            status=BondStatus.ENDED,
            ended_at=factory.Faker("date_time_this_month", tzinfo=datetime.UTC),
        )


class MoodLogFactory(DjangoModelFactory):
    class Meta:
        model = MoodLog

    patient = factory.SubFactory(PatientProfileFactory)
    mood = MoodLevel.NEUTRAL
    is_shared_with_psychologist = False


class JournalEntryFactory(DjangoModelFactory):
    class Meta:
        model = JournalEntry

    patient = factory.SubFactory(PatientProfileFactory)
    kind = JournalEntryKind.SITUATION
    title = ""
    content = factory.Faker("paragraph", locale="pt_BR")
    mood = None
    is_shared_with_psychologist = False


class ClinicalNoteFactory(DjangoModelFactory):
    class Meta:
        model = ClinicalNote

    bond = factory.SubFactory(BondFactory, active=True)
    content = factory.Faker("paragraph", locale="pt_BR")
    session_date = None
