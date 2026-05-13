"""Adiciona campo `plan` em HealthcareProvider.

Ver ADR 0010. Default basic — profissional novo nasce sem IA.
"""

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_healthcareprovider"),
    ]

    operations = [
        migrations.AddField(
            model_name="healthcareprovider",
            name="plan",
            field=models.CharField(
                choices=[
                    ("basic", "Básico"),
                    ("pro", "Pro"),
                    ("premium", "Premium"),
                ],
                default="basic",
                help_text=(
                    "Tier de assinatura. Define acesso a IA e cota — "
                    "ver ADR 0010. Profissional novo nasce em Básico "
                    "(sem IA) por default."
                ),
                max_length=10,
                verbose_name="plano",
            ),
        ),
    ]
