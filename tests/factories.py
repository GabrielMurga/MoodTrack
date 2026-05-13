"""Factories para testes — uso de factory-boy.

CLAUDE.md: usar factory-boy para fixtures, não dados hardcoded.
"""

from __future__ import annotations

import datetime

import factory
from factory.django import DjangoModelFactory

from apps.accounts.models import (
    HealthcareProvider,
    PatientProfile,
    ProviderKind,
    ProviderPlan,
    User,
)
from apps.bonds.models import Bond, BondStatus
from apps.clinical.models import (
    Medication,
    PatientOverview,
    PatientReportedMedication,
)
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


class HealthcareProviderFactory(DjangoModelFactory):
    class Meta:
        model = HealthcareProvider

    user = factory.SubFactory(UserFactory)
    kind = ProviderKind.PSYCHOLOGIST
    crp_number = factory.Sequence(lambda n: f"06/{10000 + n:05d}")
    crm_number = ""
    bio = ""
    # Default plan = basic (sem IA). Testes que precisam de IA habilitada
    # passam plan=ProviderPlan.PRO ou usam o trait pro_plan.
    plan = ProviderPlan.BASIC

    class Params:
        # Traits para criar profissional já como psiquiatra (CRM em vez de CRP).
        psychiatrist = factory.Trait(
            kind=ProviderKind.PSYCHIATRIST,
            crp_number="",
            crm_number=factory.Sequence(lambda n: f"SP/{20000 + n:05d}"),
        )
        # Trait pra promover diretamente a Pro (com IA habilitada).
        pro_plan = factory.Trait(plan=ProviderPlan.PRO)
        premium_plan = factory.Trait(plan=ProviderPlan.PREMIUM)


class PsychiatristProviderFactory(HealthcareProviderFactory):
    """Factory que cria HealthcareProvider já como psiquiatra."""

    kind = ProviderKind.PSYCHIATRIST
    crp_number = ""
    crm_number = factory.Sequence(lambda n: f"SP/{20000 + n:05d}")


class PatientProfileFactory(DjangoModelFactory):
    class Meta:
        model = PatientProfile

    user = factory.SubFactory(UserFactory)
    preferred_name = factory.Faker("first_name", locale="pt_BR")


class BondFactory(DjangoModelFactory):
    class Meta:
        model = Bond

    provider = factory.SubFactory(HealthcareProviderFactory)
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
            provider_confirmed_at=factory.Faker("date_time_this_month", tzinfo=datetime.UTC),
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
    is_shared_with_provider = False


class JournalEntryFactory(DjangoModelFactory):
    class Meta:
        model = JournalEntry

    patient = factory.SubFactory(PatientProfileFactory)
    kind = JournalEntryKind.SITUATION
    title = ""
    content = factory.Faker("paragraph", locale="pt_BR")
    mood = None
    is_shared_with_provider = False


class ClinicalNoteFactory(DjangoModelFactory):
    class Meta:
        model = ClinicalNote

    bond = factory.SubFactory(BondFactory, active=True)
    content = factory.Faker("paragraph", locale="pt_BR")
    session_date = None


class PatientOverviewFactory(DjangoModelFactory):
    class Meta:
        model = PatientOverview

    patient = factory.SubFactory(PatientProfileFactory)
    summary = factory.Faker("paragraph", locale="pt_BR")
    last_edited_by = None


class MedicationFactory(DjangoModelFactory):
    class Meta:
        model = Medication

    patient = factory.SubFactory(PatientProfileFactory)
    # Default: prescribed_by é um psiquiatra (precisa pra passar em can_prescribe).
    prescribed_by = factory.SubFactory(PsychiatristProviderFactory)
    name = factory.Faker("word", locale="pt_BR")
    dosage = "50mg"
    frequency = "1x ao dia"
    notes = ""
    started_at = factory.Faker("date_this_year")
    ended_at = None


class PatientReportedMedicationFactory(DjangoModelFactory):
    class Meta:
        model = PatientReportedMedication

    patient = factory.SubFactory(PatientProfileFactory)
    content = factory.Faker("paragraph", locale="pt_BR")
