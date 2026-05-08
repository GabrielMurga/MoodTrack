# ADR 0002 — PostgreSQL como banco de dados

**Status:** aceito
**Data:** 2026-05-08

## Contexto

O MoodTrack persiste dados sensíveis de saúde mental: registros do paciente,
anotações clínicas do psicólogo, transcrições, vínculos terapêuticos, trilha de
auditoria append-only e (futuramente) embeddings vetoriais para análise de
padrões. Os requisitos do banco incluem:

- Integridade transacional forte (um vínculo paciente-psicólogo é confirmado
  pelos dois lados — não pode ficar em estado parcial).
- Suporte a campos JSON ricos para metadados de registros sem proliferar
  tabelas.
- Full-text search em português, para o psicólogo conseguir buscar por temas
  no histórico do paciente.
- Auditoria append-only com possibilidade de revogar permissão de UPDATE/DELETE
  no nível do banco.
- Extensões maduras para criptografia (`pgcrypto`) e, em v2, vetorização
  (`pgvector`).

## Decisão

Adotar **PostgreSQL 16** como banco principal em todos os ambientes (dev,
staging, prod).

## Alternativas consideradas

- **MySQL 8.** Maduro e suportado pelo Django, mas:
  - JSON funcional, porém menos performático que JSONB para queries complexas.
  - Full-text search em pt-BR mais limitado.
  - Sem `pgvector` equivalente nativo de qualidade.
  - Triggers e revogação fina de privilégios menos ergonômicas.
- **SQLite.** Descartado para produção pelos motivos óbvios (concorrência,
  ausência de `JSONB` indexável, sem extensões críticas). Também descartado em
  dev — divergir de Postgres em dev gera surpresas em migrations e em
  comportamento de tipos.
- **MongoDB / DBs documentais.** Não são adequados ao modelo relacional do
  MoodTrack, onde a maioria das queries cruza paciente, psicólogo, registros e
  consentimentos. Acabaríamos reimplementando integridade referencial.

## Consequências

**Positivas:**
- JSONB nativo com índices GIN — bom para metadados de registro, configs
  de consentimento granular, e payloads de auditoria.
- Full-text search com configuração `portuguese` integrada.
- `pgcrypto` permite primitivas criptográficas no banco quando útil (preferimos,
  contudo, criptografia em nível de aplicação para campos sensíveis — ver ADR
  futura sobre criptografia).
- Caminho claro para `pgvector` em v2 sem trocar de banco.
- `LISTEN/NOTIFY` disponível como mecanismo leve para eventos, embora Celery
  + Redis siga como fila principal.

**Negativas:**
- Operação local exige Postgres rodando, vs SQLite que seria só um arquivo.
  Trade-off aceito pelo paralelismo dev/prod.
- Backups, vacuum tuning e replicação demandam mais cuidado operacional que
  alternativas mais simples — mas isso vem com qualquer banco que aguente o
  volume real do produto.
