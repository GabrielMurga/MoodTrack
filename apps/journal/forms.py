from django import forms
from django.utils.translation import gettext_lazy as _

from .models import ClinicalNote, JournalEntry, MoodLevel, MoodLog


class MoodLogForm(forms.ModelForm):
    class Meta:
        model = MoodLog
        fields = ("mood", "is_shared_with_provider")
        widgets = {"mood": forms.RadioSelect()}
        labels = {
            "is_shared_with_provider": _("Compartilhar com meu profissional"),
        }


class JournalEntryForm(forms.ModelForm):
    # Mood é IntegerField com choices null=True; precisa de widget que aceite "sem humor".
    mood = forms.TypedChoiceField(
        label=_("Humor associado (opcional)"),
        choices=[("", "—"), *MoodLevel.choices],
        coerce=lambda v: int(v) if v else None,
        empty_value=None,
        required=False,
    )

    class Meta:
        model = JournalEntry
        fields = ("kind", "title", "content", "mood", "is_shared_with_provider")
        widgets = {
            "content": forms.Textarea(
                attrs={
                    "rows": 6,
                    "placeholder": "Descreva o que aconteceu, o que pensou, o que sentiu…",
                }
            ),
        }
        labels = {
            "is_shared_with_provider": _("Compartilhar com meu profissional"),
        }


class ClinicalNoteForm(forms.ModelForm):
    class Meta:
        model = ClinicalNote
        fields = ("session_date", "content")
        widgets = {
            "session_date": forms.DateInput(attrs={"type": "date"}),
            "content": forms.Textarea(
                attrs={
                    "rows": 8,
                    "placeholder": "Anotações da sessão, hipóteses, plano para a próxima…",
                }
            ),
        }
