"""Renomeia PsychologistProfile -> HealthcareProvider e adiciona kind/CRM.

Ver ADR 0009. Migration não destrutiva: RenameModel + AddField + RunPython
para preencher kind nas linhas existentes (todos psicólogos hoje).

A constraint de consistência kind/registro entra ao final, depois do backfill.
"""

from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def set_kind_psychologist_on_existing(apps, schema_editor):
    """Toda linha pré-existente é psicólogo (era PsychologistProfile)."""
    HealthcareProvider = apps.get_model("accounts", "HealthcareProvider")
    HealthcareProvider.objects.filter(kind="").update(kind="psychologist")


def reverse_set_kind(apps, schema_editor):
    """Reverso é no-op — kind volta a ser irrelevante após RenameModel reverso."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_patientprofile_psychologistprofile"),
        # Aguarda a migration que cria Bond com FK para PsychologistProfile,
        # caso contrário a renomeação aqui rodaria antes da FK ser criada
        # e a referência string `accounts.psychologistprofile` em bonds/0001
        # falharia no resolve.
        ("bonds", "0001_initial"),
    ]

    operations = [
        # 1. Renomeia o model: PsychologistProfile -> HealthcareProvider.
        migrations.RenameModel(
            old_name="PsychologistProfile",
            new_name="HealthcareProvider",
        ),
        # 2. Atualiza related_name no OneToOne com User.
        migrations.AlterField(
            model_name="healthcareprovider",
            name="user",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="provider_profile",
                to=settings.AUTH_USER_MODEL,
                verbose_name="usuário",
            ),
        ),
        # 3. Adiciona o campo kind. Default temporário "" só pro backfill;
        # o RunPython logo abaixo preenche com "psychologist".
        migrations.AddField(
            model_name="healthcareprovider",
            name="kind",
            field=models.CharField(
                choices=[
                    ("psychologist", "Psicólogo"),
                    ("psychiatrist", "Psiquiatra"),
                ],
                default="",
                max_length=20,
                verbose_name="tipo de profissional",
            ),
            preserve_default=False,
        ),
        # 4. Backfill: tudo que existia é psicólogo.
        migrations.RunPython(
            set_kind_psychologist_on_existing,
            reverse_code=reverse_set_kind,
        ),
        # 5. Adiciona crm_number (vazio nos psicólogos existentes).
        migrations.AddField(
            model_name="healthcareprovider",
            name="crm_number",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Número do CRM (Conselho Regional de Medicina). "
                    "Preenchido apenas quando o tipo é psiquiatra. "
                    "Validação de formato é futura."
                ),
                max_length=20,
                verbose_name="CRM",
            ),
        ),
        # 6. Atualiza help_text do crp_number (apenas para psicólogos).
        migrations.AlterField(
            model_name="healthcareprovider",
            name="crp_number",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Número do CRP (Conselho Regional de Psicologia). "
                    "Preenchido apenas quando o tipo é psicólogo. "
                    "Validação de formato é futura."
                ),
                max_length=20,
                verbose_name="CRP",
            ),
        ),
        # 7. Atualiza verbose_name/plural do model.
        migrations.AlterModelOptions(
            name="healthcareprovider",
            options={
                "verbose_name": "perfil de profissional",
                "verbose_name_plural": "perfis de profissional",
            },
        ),
        # 8. Constraint: kind=psychologist exige crm_number vazio,
        #    kind=psychiatrist exige crp_number vazio.
        migrations.AddConstraint(
            model_name="healthcareprovider",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(kind="psychologist", crm_number="")
                    | models.Q(kind="psychiatrist", crp_number="")
                ),
                name="provider_register_number_matches_kind",
            ),
        ),
    ]
