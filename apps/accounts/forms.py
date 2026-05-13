"""Formulários de onboarding — criação de perfil após login.

User com OAuth já criado mas sem perfil escolhe ser paciente ou profissional.
Profissional ainda escolhe entre psicólogo e psiquiatra (ADR 0009).
"""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import HealthcareProvider, PatientProfile, ProviderKind


class ProviderProfileForm(forms.ModelForm):
    """Cria HealthcareProvider para o User logado.

    `kind` define se CRP ou CRM é exigido. Validação de consistência roda
    em duas camadas: aqui (mensagem amigável) e no model.clean()/CheckConstraint
    (defesa em profundidade — fail-closed mesmo se o form for ignorado).
    """

    class Meta:
        model = HealthcareProvider
        fields = ("kind", "crp_number", "crm_number", "bio")
        widgets = {
            "kind": forms.RadioSelect(),
            "bio": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Apresentação profissional curta. Visível para os pacientes vinculados.",
                }
            ),
        }
        labels = {
            "kind": _("Você é"),
            "crp_number": _("CRP (preenche apenas se for psicólogo)"),
            "crm_number": _("CRM (preenche apenas se for psiquiatra)"),
            "bio": _("Biografia profissional (opcional)"),
        }

    def clean(self) -> dict:
        cleaned = super().clean()
        kind = cleaned.get("kind")
        crp = cleaned.get("crp_number", "").strip()
        crm = cleaned.get("crm_number", "").strip()

        if kind == ProviderKind.PSYCHOLOGIST:
            if not crp:
                self.add_error("crp_number", _("CRP é obrigatório para psicólogo."))
            if crm:
                self.add_error("crm_number", _("Psicólogo não preenche CRM."))
        elif kind == ProviderKind.PSYCHIATRIST:
            if not crm:
                self.add_error("crm_number", _("CRM é obrigatório para psiquiatra."))
            if crp:
                self.add_error("crp_number", _("Psiquiatra não preenche CRP."))

        return cleaned


class PatientProfileForm(forms.ModelForm):
    class Meta:
        model = PatientProfile
        fields = ("preferred_name", "birth_date")
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {
            "preferred_name": _("Nome preferido"),
            "birth_date": _("Data de nascimento (opcional)"),
        }
