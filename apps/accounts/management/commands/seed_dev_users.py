"""Cria usuários de desenvolvimento com perfis pré-configurados.

Bloqueado fora de DEBUG para evitar criação acidental em produção.

Cria:
- psicologa@dev.local — só PsychologistProfile
- paciente@dev.local — só PatientProfile
- dual@dev.local     — ambos os perfis (psicóloga que também faz terapia)

Senha de todos: dev123
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import PatientProfile, PsychologistProfile, User

DEV_PASSWORD = "dev123"

DEV_USERS = [
    {
        "email": "psicologa@dev.local",
        "full_name": "Dra. Ana Mendes",
        "psychologist": {"crp_number": "06/12345", "bio": "Psicóloga clínica."},
        "patient": None,
    },
    {
        "email": "paciente@dev.local",
        "full_name": "Bruno Costa",
        "psychologist": None,
        "patient": {"preferred_name": "Bruno"},
    },
    {
        "email": "dual@dev.local",
        "full_name": "Dra. Camila Souza",
        "psychologist": {"crp_number": "06/67890", "bio": "Psicóloga e também em terapia."},
        "patient": {"preferred_name": "Camila"},
    },
]


class Command(BaseCommand):
    help = "Cria usuários de desenvolvimento com perfis (apenas em DEBUG=True)."

    def handle(self, *args, **options) -> None:
        if not settings.DEBUG:
            raise CommandError(
                "seed_dev_users só roda com DEBUG=True. Em produção é bloqueado."
            )

        with transaction.atomic():
            for spec in DEV_USERS:
                user, created = User.objects.get_or_create(
                    email=spec["email"],
                    defaults={"full_name": spec["full_name"]},
                )
                if created:
                    user.set_password(DEV_PASSWORD)
                    user.save()
                    self.stdout.write(self.style.SUCCESS(f"+ User: {user.email}"))
                else:
                    self.stdout.write(f"= User existente: {user.email}")

                if spec["psychologist"]:
                    _, p_created = PsychologistProfile.objects.get_or_create(
                        user=user, defaults=spec["psychologist"]
                    )
                    if p_created:
                        self.stdout.write(self.style.SUCCESS("  + PsychologistProfile"))

                if spec["patient"]:
                    _, p_created = PatientProfile.objects.get_or_create(
                        user=user, defaults=spec["patient"]
                    )
                    if p_created:
                        self.stdout.write(self.style.SUCCESS("  + PatientProfile"))

        self.stdout.write(self.style.SUCCESS(f"\nSenha de todos: {DEV_PASSWORD}"))
