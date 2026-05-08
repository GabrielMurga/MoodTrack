# MoodTrack

Plataforma de acompanhamento contínuo da saúde mental que conecta psicólogos e pacientes em um ambiente seguro, com registro estruturado do cotidiano emocional, organização clínica e análises automatizadas de padrões via IA.

## Status

🚧 Em desenvolvimento — fase inicial (MVP).

## Documentação

- [`docs/vision.md`](docs/vision.md) — Visão de produto: perfis, fluxos, ética e princípios norteadores.
- [`docs/tech-spec.md`](docs/tech-spec.md) — Especificação técnica: stack, segurança, arquitetura, escopo de MVP.
- [`docs/adr/`](docs/adr/) — Architecture Decision Records.
- [`CLAUDE.md`](CLAUDE.md) — Instruções e regras inegociáveis do projeto (também usado pelo Claude Code).

## Stack (resumo)

- **Backend:** Python 3.11 + Django 5 + Django REST Framework
- **Banco:** PostgreSQL 16
- **Web:** Django Templates + HTMX + Tailwind CSS + Alpine.js
- **Filas:** Celery + Redis
- **IA:** Anthropic Claude API com pseudonimização via spaCy + Microsoft Presidio
- **Auth:** OAuth Google (django-allauth)

## Princípios

1. Cuidado humano em primeiro lugar — a tecnologia serve à relação terapêutica, não a substitui.
2. Autonomia do paciente — controle granular de privacidade em cada registro.
3. Apoio ao profissional — ferramentas que organizam informação e qualificam decisões.
4. Responsabilidade com dados sensíveis — segurança e LGPD como pilares fundacionais, não preocupações secundárias.

## Licença

A definir.