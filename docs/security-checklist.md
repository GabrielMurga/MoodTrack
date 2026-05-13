# Security Checklist

Status atual da postura de segurança do MoodTrack e o que falta antes de
qualquer usuário real (PII real) tocar o sistema.

LGPD e a sensibilidade dos dados (saúde mental) não negociam — esta lista
é a porta de entrada pra produção, não item de "nice to have".

Convenção: ✅ feito · ⚠️ parcial · ❌ pendente · 🟡 fora do escopo do MVP

---

## 1. Bloqueantes pré-produção

Não é admissível subir pra produção com qualquer destes ❌ ou ⚠️:

- ⚠️ **OAuth Google ativo, senha desativada para usuários finais.**
  Hoje qualquer User pode logar com senha (necessário pra dev/createsuperuser).
  Em produção: superuser-com-senha continua existindo só pra ops; signup público
  e login de paciente/psicólogo passa exclusivamente por OAuth (CLAUDE.md
  regra 12).
- ❌ **`SECRET_KEY` real vinda de secret manager**, nunca commitada, nunca
  default. `config/settings/development.py` tem default insecuro intencional
  pra dev — em prod, `env("SECRET_KEY")` precisa estourar se não vier.
- ❌ **`FIELD_ENCRYPTION_KEY` real, gerenciada em secret manager separado do
  backup do banco** (ADR 0006). Hoje há chave dev no `.env.example` —
  comprometedor se alguém clonar e usar como base sem trocar.
- ❌ **ZDR (Zero Data Retention) habilitado na conta Anthropic** antes da
  primeira chamada com dados reais (CLAUDE.md regra 14). Status precisa estar
  documentado no README com data de verificação.
- ❌ **Pseudonimização ativa** em todo dado de paciente que sai pra LLM
  (CLAUDE.md regra 1). Sem isso, **nenhuma chamada à IA pode acontecer**.
- ❌ **`REVOKE UPDATE, DELETE ON audit_auditlog FROM moodtrack;`** em todos
  os ambientes não-dev. Hoje o append-only é só camada de aplicação; bug ou
  acesso direto ao DB pode adulterar histórico (CLAUDE.md regra 8).
- ❌ **Headers de segurança ativos**: HSTS (`SECURE_HSTS_SECONDS`,
  `SECURE_HSTS_INCLUDE_SUBDOMAINS`, `SECURE_HSTS_PRELOAD`), Content Security
  Policy (`django-csp`), `X-Content-Type-Options`. Stub presente em
  `production.py`, falta valores reais quando o domínio for fixado.
- ❌ **Auditoria de login** (`login.success`, `login.failed`) — operação
  sensível por definição (CLAUDE.md regra 8 inclui leitura). Importante pra
  detectar tentativas de força bruta antes do rate limit pegar.
- ❌ **Rate limiting** em endpoints sensíveis: login, formulário de inserir
  invite code, geração de invite. Sem isso, brute force é viável.
- ❌ **Fluxo LGPD do titular**: export de dados, correção, exclusão real
  (com cascata correta + audit do delete). Hoje só `is_active = False` está
  disponível; regra 5 dos direitos do titular exige mais.

## 2. Já implementado e testado

Confirmado em código + testes:

- ✅ **Criptografia em nível de aplicação** dos campos sensíveis
  (`MoodEntry.content`) via Fernet — chave separada do DB (ADR 0006).
- ✅ **Default privado** (`is_shared_with_provider=False`) — CLAUDE.md
  regra 3.
- ✅ **Vínculo paciente-profissional de dois lados** com state machine
  (CLAUDE.md regra 4).
- ✅ **Fail-closed em queryset** — `Bond.objects.for_user/for_provider
  /for_patient`, `MoodLog.objects.shared_with_provider`. Sem perfil
  ou sem bond ativo retorna queryset vazio (CLAUDE.md regras 5, 6, 7).
- ✅ **Validação de input via Forms** — DRF ainda não usado, formulários
  Django cobrem o que existe (CLAUDE.md regra 9).
- ✅ **Sem raw SQL com input do usuário** — ORM em todo lugar (CLAUDE.md
  regra 10).
- ✅ **AuditLog append-only em camada de aplicação**: `save()` recusa
  UPDATE; `delete()` recusa. Testado.
- ✅ **CSRF protection** — Django default + `{% csrf_token %}` em todos os
  forms.
- ✅ **XSS protection** — Django auto-escape default; templates usam
  `{{ var }}` sem `|safe` em conteúdo de paciente.
- ✅ **`.env` no `.gitignore`**, segredos não commitados.
- ✅ **Self-bond bloqueado** — paciente não pode usar próprio invite code
  (mesmo no caso dual psicóloga + paciente).
- ✅ **`AUTH_USER_MODEL` customizado** com email único; sem `username` que
  pudesse virar enumeration vector.
- ✅ **Senha hasheada com PBKDF2** (Django default) — relevante apenas
  para superuser de ops, fluxo público é OAuth.

## 3. Defense-in-depth (não bloqueante mas relevante)

Adicionar antes de passar de "alguns pacientes piloto" pra "produto público":

- ❌ **`SECURE_PROXY_SSL_HEADER`** validado para o reverse proxy real.
- ❌ **Cookies session/CSRF com `SameSite=Strict`** se UX permitir.
- ❌ **Logging estruturado** com retenção definida e PII filtrada (CLAUDE.md
  regra 15: logs de chamadas externas sem conteúdo).
- ❌ **Backup do banco com criptografia em repouso** + chave de cripto
  separada do backup.
- ❌ **Rotação de chave de criptografia** documentada e testada
  (`FIELD_ENCRYPTION_KEYS` aceita lista pra rotação suave).
- ❌ **Análise estática de segurança** no CI (Bandit, Semgrep).
- ❌ **Dependabot/uv lock auditing** ativado.

## 4. Fora do escopo do MVP (consciente)

Itens que tech-spec.md ou CLAUDE.md marcaram como pós-MVP:

- 🟡 **2FA** — psicólogo entra com Google só, no MVP. 2FA TOTP/WebAuthn
  fica pra v2.
- 🟡 **Apple Sign-In** — entra com app mobile (RN) na v2.
- 🟡 **Modo de apoio em crise interativo** — link estático para CVV resolve
  no MVP.
- 🟡 **Áudio + transcrição (Whisper)** — v2.
- 🟡 **Escalas clínicas validadas (PHQ-9, GAD-7)** — v2.

## 5. Política de revisão

Revisar este documento:

1. **Antes de cada novo deploy a ambiente exposto** (mesmo staging com
   dados sintéticos).
2. **Quando uma fatia tocar dados sensíveis** (qualquer mudança em
   `apps/audit`, `apps/journal`, `apps/accounts` ou que envolva chamada
   externa).
3. **Antes do primeiro usuário real** — checklist da seção 1 precisa
   estar 100% verde.
