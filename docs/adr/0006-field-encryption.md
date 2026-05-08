# ADR 0006 — Biblioteca de criptografia de campos

**Status:** aceito
**Data:** 2026-05-08

## Contexto

CLAUDE.md regra 2 exige que campos sensíveis (anotações de paciente,
transcrições, anotações clínicas, conteúdo de registros) sejam
criptografados em nível de aplicação, com chaves gerenciadas
separadamente do banco. A regra cita explicitamente `django-cryptography`
ou `django-fernet-fields` como referências.

Ao avaliar para implementação real:

- **django-cryptography** (georgemarshall/django-cryptography): o pacote
  original. Última release na PyPI > 12 meses atrás; o projeto
  é considerado abandonado. Sem suporte oficial a Django 5.x.
- **django-fernet-fields**: similar, também não atualizado.
- **django-cryptography-django5**: fork específico para Django 5,
  status "Pre-Alpha", última release jun/2024. Não adequado para produção.
- **django-cryptography-5** (czue/django-cryptography-5): fork mantido
  com release jan/2025, suporte explícito Django 5.0 e 5.1, API drop-in
  compatível com django-cryptography original. Sole maintainer (risco
  de bus factor), mas estável e auditável.
- **django-encrypted-field**: pacote novo, release abr/2026, usa
  ChaCha20-Poly1305 (AEAD moderno). API diferente, sole maintainer
  também, mas primitivas mais modernas.

Outros critérios:

- Os dados em jogo (texto livre de paciente sobre estado emocional,
  pensamentos, sonhos) são "categoria sensível" pela LGPD. Algoritmo
  precisa ser reconhecido e bem auditado, não experimental.
- Queries não precisam filtrar/ordenar por conteúdo criptografado
  (limitação aceitável de qualquer field encryption).
- Rotação de chaves precisa ser viável no longo prazo. Não é parte do
  MVP, mas a lib não pode bloquear o caminho.

## Decisão

Adotar **`django-cryptography-5`** como biblioteca de criptografia de
campos no MoodTrack. Usar `encrypt(...)` em torno de campos com dado
sensível.

**Algoritmo:** Fernet (AES-128-CBC + HMAC-SHA256). Especificação
publicada (cryptography.io), uso amplo em Python, NIST-aprovado.

**Chave:** `FIELD_ENCRYPTION_KEY` lida do ambiente em
`config/settings/base.py`. Em desenvolvimento, valor placeholder no
`.env.example`. Em produção, chave gerada com
`Fernet.generate_key()` e armazenada em secret manager separado do
banco — nunca no repositório, nunca no mesmo cofre que o backup do DB.

## Alternativas consideradas

- **django-encrypted-field** (ChaCha20-Poly1305): primitiva
  criptográfica moderna (AEAD, mesmo algoritmo do TLS 1.3), mas API
  diferente da que CLAUDE.md cita. Para MVP, valor da continuidade
  com a especificação supera ganho marginal de algoritmo. Pode ser
  reavaliada em hardening pós-MVP.
- **django-cryptography original**: descartada por estar abandonada;
  django-cryptography-5 é o caminho de migração.
- **Criptografia em nível de coluna no Postgres** (`pgcrypto`):
  exige a chave estar acessível ao DB, contradizendo regra 2 que pede
  chaves gerenciadas separadamente. Mantida como recurso para casos
  específicos (não para campos sensíveis de paciente).
- **Aplicação de cripto manual** (chamadas diretas a `cryptography`
  package em managers/signals): evita dependência extra mas reinventa
  o que `django-cryptography-5` já entrega bem testado. Custo > benefício.

## Consequências

**Positivas:**
- Mantém spec do CLAUDE.md (regra 2 satisfeita com a lib citada).
- API simples — `encrypt(models.TextField())` em substituição direta
  ao field não criptografado.
- Algoritmo Fernet é estável, bem documentado, sem CVEs relevantes.
- Caminho claro de rotação: `FIELD_ENCRYPTION_KEYS` aceita lista de
  chaves (lê com a primeira que decifrar; cifra sempre com a primeira).

**Negativas:**
- Sole maintainer da lib (risco de descontinuidade futura). Mitigação:
  a API é fina; trocar para alternativa exige migration de dados +
  reescrita de declarações de campo, mas é plano feasible.
- Queries não podem filtrar por conteúdo criptografado. Aceitável:
  busca em conteúdo de paciente é sensível por design — onde for
  necessário, será via pseudonimização + index separado, não via DB
  direto.
- Performance: cada decrypt acontece no app server, não no DB. Em
  listas longas, custo se acumula. Mitigação: paginar; em queries em
  massa, considerar batch decrypt fora do ORM.
- Backup do banco contém ciphertext mas não a chave. Operação precisa
  garantir que a chave seja protegida tão fortemente quanto o backup.

## Operação

- **Geração da chave** (uma vez por ambiente):
  ```python
  from cryptography.fernet import Fernet
  print(Fernet.generate_key().decode())
  ```
- **Rotação**: documentar quando precisar. Por enquanto, fora do MVP.
- **Perda da chave = perda dos dados.** Backup da chave é
  responsabilidade operacional crítica.
