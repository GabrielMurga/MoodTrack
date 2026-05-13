from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Bond


class CreateInviteForm(forms.ModelForm):
    """Profissional cria convite com um rótulo livre pra lembrar de quem é."""

    class Meta:
        model = Bond
        fields = ["invitee_label"]
        widgets = {
            "invitee_label": forms.TextInput(
                attrs={
                    "placeholder": "Ex: João Silva, joao@email.com, nova paciente terça",
                    "autocomplete": "off",
                }
            ),
        }
        labels = {"invitee_label": _("Para quem é este convite?")}


class EnterInviteCodeForm(forms.Form):
    """Formulário do paciente — recebe o código que o psicólogo gerou."""

    invite_code = forms.CharField(
        label=_("Código de convite"),
        max_length=12,
        min_length=8,
        strip=True,
        help_text=_("Código de 8 caracteres fornecido pelo seu psicólogo."),
        widget=forms.TextInput(attrs={"autocapitalize": "characters", "autocomplete": "off"}),
    )

    def clean_invite_code(self) -> str:
        code = self.cleaned_data["invite_code"].upper().strip()
        try:
            bond = Bond.objects.get(invite_code=code)
        except Bond.DoesNotExist as exc:
            raise forms.ValidationError(_("Código não encontrado.")) from exc

        from .models import BondStatus

        if bond.status != BondStatus.INVITED:
            raise forms.ValidationError(_("Esse código já foi utilizado ou não é mais válido."))
        self.bond = bond
        return code
