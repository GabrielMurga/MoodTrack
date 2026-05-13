"""Renomeia FK Bond.psychologist -> Bond.provider e timestamp correlato.

Acompanha ADR 0009. Não destrutivo: usa RenameField + ajusta constraint
unique para refletir o novo nome.
"""

from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_healthcareprovider"),
        ("bonds", "0001_initial"),
    ]

    operations = [
        # 1. Remove a constraint única que referencia o nome antigo.
        migrations.RemoveConstraint(
            model_name="bond",
            name="unique_alive_bond_per_pair",
        ),
        # 2. Renomeia FK psychologist -> provider.
        migrations.RenameField(
            model_name="bond",
            old_name="psychologist",
            new_name="provider",
        ),
        # 3. Renomeia timestamp psychologist_confirmed_at -> provider_confirmed_at.
        migrations.RenameField(
            model_name="bond",
            old_name="psychologist_confirmed_at",
            new_name="provider_confirmed_at",
        ),
        # 4. Aponta a FK pro novo model HealthcareProvider e ajusta verbose_name.
        migrations.AlterField(
            model_name="bond",
            name="provider",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="bonds",
                to="accounts.healthcareprovider",
                verbose_name="profissional",
            ),
        ),
        # 5. Atualiza verbose_name do timestamp.
        migrations.AlterField(
            model_name="bond",
            name="provider_confirmed_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="profissional confirmou em",
            ),
        ),
        # 6. Recria a constraint única com o novo nome do campo.
        migrations.AddConstraint(
            model_name="bond",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status__in", ("invited", "pending", "active"))),
                fields=("provider", "patient"),
                name="unique_alive_bond_per_pair",
            ),
        ),
    ]
