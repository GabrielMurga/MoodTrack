"""Cria AIUsageCounter — contador mensal por profissional.

Acompanha ADR 0010. Contador é coarse-grained (uma linha por mês), serve
para comparação rápida contra cota do plano.
"""

from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_provider_plan"),
        ("ai", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AIUsageCounter",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "period",
                    models.DateField(
                        db_index=True,
                        help_text=(
                            "Primeiro dia do mês a que se refere a contagem. "
                            "Reset implícito: novo mês = nova linha."
                        ),
                        verbose_name="período (1º dia do mês)",
                    ),
                ),
                (
                    "count",
                    models.PositiveIntegerField(default=0, verbose_name="usos no período"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="atualizado em"),
                ),
                (
                    "provider",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ai_usage_counters",
                        to="accounts.healthcareprovider",
                        verbose_name="profissional",
                    ),
                ),
            ],
            options={
                "verbose_name": "contador de uso de IA",
                "verbose_name_plural": "contadores de uso de IA",
                "indexes": [
                    models.Index(
                        fields=["provider", "-period"],
                        name="ai_aiusageco_provide_3df1d2_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("provider", "period"),
                        name="unique_ai_usage_counter_per_period",
                    ),
                ],
            },
        ),
    ]
