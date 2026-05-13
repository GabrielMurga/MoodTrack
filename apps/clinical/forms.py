from __future__ import annotations

from django import forms

from .models import Medication, PatientReportedMedication


class MedicationForm(forms.ModelForm):
    class Meta:
        model = Medication
        fields = ["name", "dosage", "frequency", "notes", "started_at"]
        widgets = {
            "started_at": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "name": "Medicamento",
            "dosage": "Dosagem",
            "frequency": "Frequência",
            "notes": "Observações",
            "started_at": "Data de início",
        }


class PatientReportedMedicationForm(forms.ModelForm):
    class Meta:
        model = PatientReportedMedication
        fields = ["content"]
        widgets = {
            "content": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Liste o que está tomando: remédios, dosagens, suplementos…",
                }
            ),
        }
        labels = {"content": "Medicações que estou tomando"}
