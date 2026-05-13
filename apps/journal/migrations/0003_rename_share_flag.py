"""Renomeia is_shared_with_psychologist -> is_shared_with_provider.

Em MoodLog e JournalEntry. Acompanha ADR 0009: o flag passa a se chamar
"compartilhar com profissional" porque o vínculo agora pode ser com
psiquiatra também.
"""

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("journal", "0002_clinicalnote_journalentry_moodlog_delete_moodentry_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="moodlog",
            old_name="is_shared_with_psychologist",
            new_name="is_shared_with_provider",
        ),
        migrations.AlterField(
            model_name="moodlog",
            name="is_shared_with_provider",
            field=models.BooleanField(
                default=False,
                verbose_name="compartilhar com profissional",
            ),
        ),
        migrations.RenameField(
            model_name="journalentry",
            old_name="is_shared_with_psychologist",
            new_name="is_shared_with_provider",
        ),
        migrations.AlterField(
            model_name="journalentry",
            name="is_shared_with_provider",
            field=models.BooleanField(
                default=False,
                verbose_name="compartilhar com profissional",
            ),
        ),
    ]
