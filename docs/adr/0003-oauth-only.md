# ADR 0003 — Autenticação exclusivamente via OAuth social

**Status:** aceito
**Data:** 2026-05-08

## Contexto

O MoodTrack lida com dados de saúde mental — categoria sensível pela LGPD e
pela natureza clínica. Auth com email/senha tradicional carrega:

- Armazenamento de hashes de senha (mais um vetor de vazamento se a base for
  comprometida).
- Fluxo de reset de senha (email tokens, expiração, revogação) — superfície
  ampla, comum em incidentes.
- Risco de reuso de senha vazada de outros sites (credential stuffing).
- Necessidade de implementar e manter 2FA para chegar em postura aceitável.

A audiência principal — psicólogos em prática clínica e pacientes em terapia
no Brasil — tem, na esmagadora maioria, conta Google ativa. Apple OAuth,
Facebook ou Microsoft entram só se a evidência de uso pedir; no MVP, Google
basta.

## Decisão

Autenticação **exclusivamente via OAuth social**, com **Google** como único
provedor no MVP, implementado com `django-allauth`. Nenhum endpoint de
cadastro/login com senha. Nenhum endpoint de reset de senha. Custom User model
sem coluna `username`, com `email` como `USERNAME_FIELD` e `set_unusable_password()`
na criação.

## Alternativas consideradas

- **Email/senha + 2FA TOTP.** Postura aceitável, mas custa muito código de
  fluxo de cadastro, validação, reset, lockout, e-mail transacional, e ainda
  exige educação do usuário sobre 2FA. Para o MVP é tempo gasto onde o produto
  não tem diferencial.
- **Magic link (sem senha, só email).** Reduz superfície vs senha, mas depende
  pesadamente do canal email (entregabilidade, latência, phishing por links).
  Se o email for comprometido, a conta vai junto — sem fator adicional.
- **OAuth + senha como fallback.** Pior dos dois mundos: ainda armazena hashes
  e mantém todos os fluxos de senha, sem reduzir superfície.
- **Apple Sign-In também no MVP.** Bom valor para iOS, mas o app mobile é v2.
  Entra junto com o app.

## Consequências

**Positivas:**
- Sem senhas armazenadas → vetor de vazamento eliminado.
- Sem fluxo de reset → menos código sensível pra manter e auditar.
- 2FA delegado ao Google (que a maioria dos usuários já tem ativado).
- Identidade verificada (Google confirma o email).

**Negativas:**
- Usuário sem conta Google fica de fora no MVP. Aceitável dado o público-alvo,
  mas é uma porta fechada — registrar no roadmap a inclusão de Apple OAuth
  quando o app mobile sair, e Microsoft se evidência clínica institucional
  pedir.
- Vendor lock-in parcial em identidade. Mitigado por: o `email` permanece o
  identificador interno, então um dia trocar/somar provedor é viável sem
  perder usuários.
- Disponibilidade do login depende do Google. Indisponibilidade do provedor
  bloqueia novos logins (sessões existentes seguem). Risco aceito.
- Auditoria perde a visão "usuário trocou senha" — em troca, ganha-se "usuário
  vinculou nova conta Google" via webhooks/eventos do allauth.
