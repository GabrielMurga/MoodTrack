from django import forms

from .models import MoodEntry


class MoodEntryForm(forms.ModelForm):
    class Meta:
        model = MoodEntry
        fields = ("mood", "content", "is_shared_with_psychologist")
        widgets = {
            "mood": forms.RadioSelect(),
            "content": forms.Textarea(attrs={"rows": 5, "placeholder": "Descreva como está se sentindo, se quiser…"}),
        }
        labels = {
            "is_shared_with_psychologist": "Compartilhar este registro com meu psicólogo",
        }
