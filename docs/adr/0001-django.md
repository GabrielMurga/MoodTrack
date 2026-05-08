# ADR 0001 — Django como framework web

**Status:** aceito
**Data:** 2026-05-08

## Contexto

O MoodTrack é um produto com superfície ampla logo no MVP: autenticação social,
modelos relacionais com integridade transacional (vínculo paciente-psicólogo,
registros com flag de visibilidade, auditoria append-only), painel administrativo
para suporte interno, templates server-side, fila assíncrona para chamadas de IA,
APIs REST para o cliente web (HTMX) e — em v2 — mobile (React Native).

Precisamos de um framework Python (decisão de stack já dada por familiaridade do
time e por dependências de IA serem majoritariamente Python) que entregue boa
parte dessa superfície sem composição manual de dezenas de bibliotecas, e que
tenha ecossistema maduro para auth social, criptografia de campo e ORM com
migrations versionadas.

## Decisão

Adotar **Django 5** como framework web principal, com **Django REST Framework**
para a camada de API.

## Alternativas consideradas

- **Flask + SQLAlchemy + extensões avulsas.** Flexível, leve, mas exige montar à
  mão auth, admin, migrations (Alembic), sessions, CSRF, i18n e estrutura de
  apps. Para um produto com requisitos regulatórios (LGPD) e prontuário clínico,
  reinventar essa base custa tempo e gera superfície de bugs em camadas onde
  Django já é battle-tested.
- **FastAPI.** Excelente para APIs puras com tipagem forte, mas o MVP é
  predominantemente server-rendered (HTMX). FastAPI deixaria a camada de
  templates, sessões e admin a cargo de bibliotecas externas, anulando boa parte
  da economia. Pode entrar em v2 se uma API mobile crescer ao ponto de justificar
  serviço separado.
- **Pyramid.** Maduro, mas comunidade muito menor. Menos pacotes prontos para
  pseudonimização (Presidio), allauth, DRF, etc.

## Consequências

**Positivas:**
- Auth, admin, ORM, migrations, sessions, CSRF, i18n e signal system prontos.
- Ecossistema crítico já disponível: `django-allauth` (OAuth), `django-cryptography`
  (campos criptografados), `django-environ`, DRF.
- Convenção pesada — apps em `apps/`, settings divididos, `AUTH_USER_MODEL`
  customizado — facilita onboarding e padroniza decisões repetitivas.
- Admin built-in dá ferramenta interna de suporte sem custo extra (com cuidado
  de auditoria).

**Negativas:**
- Mais opinionado: fugir das convenções (ex.: substituir ORM por algo
  assíncrono) é caro.
- Combinação Django + DRF pode ser verbosa em endpoints simples; mitigado com
  generics e ViewSets quando o padrão se repete.
- Async ainda é limitado (Django 5.1 melhorou, mas ORM síncrono é o padrão);
  tarefas longas/IO ficam no Celery, não em views async.
