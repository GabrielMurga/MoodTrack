# MoodTrack — Instruções para o Claude Code

## O que é o projeto

MoodTrack é uma plataforma de acompanhamento de saúde mental que conecta psicólogos e pacientes. Pacientes registram seu cotidiano emocional entre sessões; psicólogos acompanham de forma organizada e recebem resumos automatizados. Há também modo individual (sem psicólogo).

Especificação completa em:
- `docs/vision.md` — visão de produto (perfis, fluxos, ética, princípios)
- `docs/tech-spec.md` — especificação técnica (stack, segurança, arquitetura)
- `docs/adr/` — Architecture Decision Records (decisões arquiteturais)

**Sempre consulte esses documentos antes de propor mudanças estruturais ou implementar features novas.**

## Stack

- **Backend:** Python 3.11 + Django 5 + Django REST Framework
- **Banco:** PostgreSQL 16
- **Web:** Django Templates + HTMX + Tailwind CSS + Alpine.js
- **Filas:** Celery + Redis
- **IA:** Anthropic Claude API (Whisper fica para v2)
- **Pseudonimização:** spaCy (pt_core_news_lg) + Microsoft Presidio
- **Auth:** django-allauth (Google OAuth)
- **Testes:** pytest + pytest-django + factory-boy
- **Lint/format:** Ruff
- **Type check:** mypy nas partes críticas

Mobile (React Native), áudio (Whisper), 2FA, escalas clínicas e sessões estruturadas estão **fora do MVP** — não implemente sem discussão prévia.

## Regras inegociáveis

Estas regras valem em **toda** decisão de código. Quando houver conflito entre conveniência e estas regras, as regras vencem.

### Privacidade e dados sensíveis

1. **Nenhum dado de paciente vai para LLM externa sem passar pelo pipeline de pseudonimização** (`apps/ai/pseudonymization.py`). Sem exceção. Mesmo em testes, mesmo em prototipagem, mesmo "só pra ver se funciona".
2. **Campos sensíveis são criptografados em nível de aplicação** com django-cryptography ou django-fernet-fields: anotações de paciente, transcrições, anotações clínicas do psicólogo, conteúdo de registros. Chaves gerenciadas separadamente do banco.
3. **Cada registro do paciente carrega flag explícita de visibilidade** (`is_shared_with_psychologist: bool`). Default é `False` (privado). Compartilhamento é decisão consciente do paciente, nunca implícita.
4. **Vínculo paciente-psicólogo exige confirmação dos dois lados.** Código de convite gerado pelo psicólogo, inserido pelo paciente, confirmado pelo psicólogo. Não há vínculo automático.

### Autorização

5. **Fail-closed sempre.** Se a verificação de permissão falhar por qualquer motivo (exceção, valor None, dado faltando), a resposta é negar acesso, nunca permitir.
6. **Psicólogo só vê pacientes vinculados a ele.** Aplicado em queryset, nunca confiando só em filtro de view. Use managers customizados ou querysets que já filtram pelo vínculo.
7. **Paciente só vê os próprios dados.** Mesma regra.
8. **Toda operação sensível (leitura ou escrita) gera registro em `apps/audit/`.** Tabela append-only (sem UPDATE/DELETE permitidos em banco).

### Validação e segurança

9. **Toda entrada de cliente passa por serializer do DRF** antes de tocar o banco. Nunca confie em dado de cliente, mesmo do próprio frontend.
10. **Nunca use raw SQL com input de usuário.** Sempre ORM. Se precisar de raw SQL, use parâmetros ligados, nunca string formatting.
11. **Try/except nunca engole erros silenciosamente em rotas sensíveis.** Logue e re-raise, ou trate explicitamente.
12. **Senhas não existem no projeto.** Auth é exclusivamente OAuth social. Não crie campos de senha, não crie endpoints de reset de senha.

### IA

13. **A IA é apoio, não substitui clínica humana.** Não escreva código que dê "conselhos clínicos" ao paciente, faça "diagnóstico", ou tome decisão em lugar do psicólogo. Geração de resumo e identificação de padrões é apoio interpretativo.
14. **Zero Data Retention** deve estar configurado na conta Anthropic antes de qualquer chamada com dados reais. Documente o status no README.
15. **Logs de chamadas a APIs externas registram metadados (usuário, timestamp, tipo de operação), nunca o conteúdo enviado/recebido.**

## Convenções de código

### Estrutura
- Apps Django ficam em `apps/` (não na raiz). Cada app tem responsabilidade clara, conforme `docs/tech-spec.md`.
- Configurações em `config/` (settings divididos por ambiente: `base.py`, `development.py`, `production.py`).
- Testes em `tests/` no nível do projeto, espelhando estrutura de `apps/`.

### Estilo Python
- Ruff é a fonte da verdade para formatação e lint. Rode `ruff check` e `ruff format` antes de commit.
- Type hints em todas as funções públicas. mypy strict nas pastas `apps/ai/`, `apps/audit/`, `apps/consent/` e `apps/accounts/` (camadas críticas).
- Docstrings em funções não triviais. Estilo Google ou NumPy, consistente.
- Nomes em inglês para código (variáveis, funções, classes). Strings de UI em português.

### Testes
- Toda feature nova vem com teste. Cobertura mínima 80% nos apps de domínio.
- Use factory-boy para fixtures, não dados hardcoded.
- Testes de autorização são obrigatórios para qualquer view nova: o teste deve verificar que usuário sem permissão recebe 403/404.
- Pseudonimização tem suite de testes específica com casos de borda (nomes compostos, locais ambíguos, datas em formatos diversos).

### Migrations
- Toda migration é revisada antes de aplicar. Migration destrutiva (drop column, drop table) requer ADR.
- Nunca aplicar migration em produção sem testar em staging primeiro.

## Comandos úteis

(Estes comandos serão configurados conforme o projeto for crescendo. Por enquanto, o projeto Django ainda não está inicializado.)

```bash
# Rodar testes
pytest

# Lint e format
ruff check .
ruff format .

# Type check
mypy apps/ai apps/audit apps/consent apps/accounts

# Server dev
python manage.py runserver

# Worker Celery
celery -A config worker -l info

# Migrations
python manage.py makemigrations
python manage.py migrate
```

## ADRs

Decisões arquiteturais ficam em `docs/adr/`. Formato: `NNNN-titulo-em-kebab-case.md`. Cada ADR contém:

- **Contexto:** o problema e suas restrições
- **Decisão:** o que foi escolhido
- **Alternativas consideradas:** o que foi descartado e por quê
- **Consequências:** o que muda no projeto (positivo e negativo)

**Crie ADR antes** de:
- Trocar lib de uma camada (ORM, fila, cache, auth)
- Mudar estratégia de segurança ou criptografia
- Adicionar dependência externa relevante
- Tomar decisão que afeta múltiplos apps

## Comportamento esperado do Claude Code

- **Pergunte antes de assumir.** Se a especificação não cobre o caso, pergunte. Não invente requisito.
- **Proponha antes de executar mudanças grandes.** Reescrita de módulo, refatoração ampla, mudança de schema — apresente plano primeiro, espere aprovação.
- **Justifique decisões.** Explique trade-offs, não só o que foi feito.
- **Não esconda problemas.** Se algo não funcionou ou ficou incompleto, diga claramente. Não maquie.
- **Respeite o escopo do MVP.** Não implemente features de v2 sem discussão.