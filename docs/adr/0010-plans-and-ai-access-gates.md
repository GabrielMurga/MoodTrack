# ADR 0010 — Planos do profissional e gates de acesso à IA

**Status:** aceito
**Data:** 2026-05-09

## Contexto

O modelo de negócio do MoodTrack tem três tiers para o profissional
(decisão de produto, fora do escopo desta ADR):

- **Básico** — mensalidade baixa, **sem acesso a IA**.
- **Pro** — mensalidade intermediária, IA com cota dimensionada para
  cobrir o custo real do uso típico.
- **Premium** — mensalidade alta, IA praticamente ilimitada
  (apenas anti-abuse).

A IA é um custo variável (chamadas a Anthropic/Claude — ver ADR 0008).
Sem gate, qualquer profissional poderia consumir IA sem limite,
quebrando a unidade econômica do produto. O sistema precisa de uma
camada explícita que decida, antes de cada chamada à LLM, se aquele
profissional tem direito ao uso e se ainda tem saldo.

Hoje em `apps/ai/views.py` existem dois pontos de chamada:

- `patient_generate_weekly` — paciente gera o próprio resumo
  semanal.
- `psychologist_generate_briefing` — profissional gera briefing
  pré-sessão para um paciente vinculado.

Outras chamadas vão aparecer (resumo do paciente para o bloco
"Resumo + Medicações", agendamento de resumos semanais por Celery,
etc.). A decisão precisa ser independente dos pontos atuais.

Há também a questão da **automação pagamento → cota**: quando
billing real existir, pagamento confirmado deve provisionar cota
sem fricção pro profissional (sem UI de "comprar tokens"). Esta
ADR não implementa billing, mas precisa deixar a forma pronta
pra plugar depois.

## Decisão

### Campo `plan` em `HealthcareProvider`

Adicionado em sequência ao ADR 0009:

```python
class ProviderPlan(models.TextChoices):
    BASIC = "basic", _("Básico")
    PRO = "pro", _("Pro")
    PREMIUM = "premium", _("Premium")


class HealthcareProvider(models.Model):
    # ... (campos do ADR 0009)
    plan = models.CharField(
        max_length=10,
        choices=ProviderPlan.choices,
        default=ProviderPlan.BASIC,
    )
```

Default `basic` significa que profissional novo não tem IA até
alguém alterar o plano. No MVP a alteração é manual (admin Django).
Quando billing real entrar, vira side-effect do webhook de pagamento.

### Schema de cota

Criar `apps/billing/` é prematuro (não há gateway integrado, não há
cobrança real). Mas a forma do contador de uso já entra:

```python
class AIUsageCounter(models.Model):
    """Contador mensal de uso de IA por profissional.

    Uma linha por (provider, ano-mês). `count` incrementa a cada
    operação de IA bem-sucedida. Reset é implícito: novo mês, nova
    linha.
    """
    provider = models.ForeignKey(HealthcareProvider, on_delete=models.CASCADE)
    period = models.DateField()  # primeiro dia do mês de referência
    count = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [("provider", "period")]
```

No MVP o contador é incrementado mas a comparação contra limite
**sempre passa** — ver "Mock de cota" abaixo. A tabela existe para
quando billing real plugar limites de verdade.

A escolha de "contador mensal genérico" em vez de "tabela detalhada
por chamada" é deliberada: detalhamento por chamada vira `apps/audit/`
(que já existe e captura metadados). `AIUsageCounter` é só pra checar
"quanto desse mês já gastou" sem fazer COUNT em audit a cada request.

### Interface `ai_access.check`

Função pura em `apps/ai/access.py`:

```python
class AIAction(StrEnum):
    WEEKLY_SUMMARY = "weekly_summary"
    SESSION_BRIEFING = "session_briefing"
    PATIENT_OVERVIEW = "patient_overview"  # bloco Resumo+Medicações
    # mais valores conforme features novas


@dataclass(frozen=True)
class Allowed:
    pass


@dataclass(frozen=True)
class NoFeature:
    """Plano do profissional não inclui IA."""
    plan: ProviderPlan


@dataclass(frozen=True)
class QuotaExceeded:
    """Cota mensal esgotada."""
    used: int
    limit: int


AccessDecision = Allowed | NoFeature | QuotaExceeded


def check(actor: User, action: AIAction) -> AccessDecision:
    """Decide se `actor` pode executar `action` agora.

    Resolve o profissional responsável pela cota:
    - Se `actor` é HealthcareProvider, é ele mesmo.
    - Se `actor` é PatientProfile com Bond ativo, é o profissional
      vinculado.
    - Se `actor` é PatientProfile em modo individual (sem Bond),
      retorna NoFeature — não há quem pague pela IA. (Decisão de
      produto: modo individual não tem IA no MVP. Reavaliar quando
      definirmos pricing pra paciente direto.)

    Fail-closed: qualquer exceção inesperada vira NoFeature.
    """
```

Quem chama interpreta o retorno e age (renderiza erro amigável,
esconde botão, registra audit).

### Mock de cota no MVP

Pro `pro` e `premium`, comparação contra limite **sempre passa**.
A função registra `AIUsageCounter` (incrementa após sucesso da
chamada), mas não bloqueia. Limites reais virão com billing.

Pra `basic`, retorno é sempre `NoFeature`.

### Plug nos pontos de chamada

Em `apps/ai/views.py`, cada view de geração faz:

```python
decision = ai_access.check(request.user, AIAction.SESSION_BRIEFING)
if isinstance(decision, NoFeature):
    messages.error(request, "Seu plano não inclui IA.")
    return redirect(...)
if isinstance(decision, QuotaExceeded):
    messages.error(request, "Você atingiu o limite mensal de uso.")
    return redirect(...)

# decisão é Allowed → segue
generate_session_briefing(...)
ai_access.record_usage(provider, AIAction.SESSION_BRIEFING)
```

`record_usage` é separado de `check` por design: incrementar antes
de saber se a chamada deu certo causaria cobrança fantasma em caso
de erro da Anthropic. Incrementar depois exige que a chamada tenha
sucedido — ver tratamento de exceção em ADR 0008.

### Fail-closed (CLAUDE.md regra 5)

Qualquer caminho não esperado em `check` retorna `NoFeature` (mais
restritivo de não-Allowed). Exceção dentro da função vira log de
audit + retorno `NoFeature`. Nunca `Allowed` por default.

### UI

Templates checam `provider.plan == ProviderPlan.BASIC` (via
template tag) e **escondem** pontos de entrada de IA. Não aparece
botão cinza, não aparece mensagem "upgrade pra usar" inline (isso
fica em página separada de comparação de planos, fora do escopo
agora).

## Alternativas consideradas

- **Permissões Django built-in (`user.has_perm("ai.can_use")`).**
  Permissões Django foram desenhadas pra controle de admin/staff
  estático, não pra gating dinâmico baseado em plano + cota. Forçar
  isso ali esconde a lógica em camadas (group ↔ permission ↔ flag),
  e dificulta testar/raciocinar sobre cota. Descartado.
- **Decorator `@requires_plan(Plan.PRO)` nas views.** Cobre a parte
  de feature gate mas não a de cota. E acopla a decisão de produto
  ao framework HTTP — mesmo gate vai precisar rodar em Celery beat
  pra resumos agendados. Descartado em favor de função pura.
- **Tabela de uso detalhada por chamada (em vez de contador mensal).**
  Já temos `apps/audit/` capturando metadados de cada chamada
  (CLAUDE.md regra 15). Duplicar geraria duas fontes de verdade.
  Contador agregado é o suficiente pra decisão; audit fica como
  fonte de detalhe.
- **Computar uso lendo audit em runtime.** Faz `COUNT` em audit a
  cada request. Audit cresce; performance degrada. Contador
  agregado custa um `INSERT ... ON CONFLICT UPDATE` por uso.
- **Contador por dia em vez de mensal.** Cobra/limita com granularidade
  diária. Útil pra Pro com "1 por paciente por dia" no longo prazo.
  Decidido manter mensal por ora; quando virar regra real, é só
  trocar `period` pra `date` e deixar a função interpretar a janela.

## Consequências

**Positivas:**

- Gate de IA isolado em uma função → fácil testar (entrada/saída
  pura), fácil mockar nos testes que não querem rodar a regra.
- Schema de cota pronto pra receber billing real sem refactor: muda
  só o "sempre passa" pra "compara contra limite do plano".
- Profissional novo nasce em Básico, sem IA — preserva margem por
  default. Migração da população existente é uma migration de dados
  (definir manualmente quem entra em Pro/Premium ou deixar todo mundo
  Básico).
- Audit log e contador agregado são complementares, não duplicados:
  audit é fonte de verdade detalhada, contador é cache de agregação
  pra gate.
- Paciente em modo individual (sem Bond) é fechado pra IA por default.
  Decisão consciente — abrir IA pra paciente sem ninguém pagando
  furava a unidade econômica.

**Negativas:**

- Contador mensal é coarse-grained. Se um Pro decidir gerar 100
  briefings no dia 1, ele bate o limite mensal e fica zero pelo
  resto do mês. Aceitável agora; granularidade fina vira ajuste no
  schema do `period` quando billing entrar.
- Esconder UI por plano significa template tags novos e duplicação
  de checagem (template e view). Mitigação: ambas chamam `ai_access`
  — uma fonte de verdade.
- Decisão de "modo individual sem IA" pode atritar com produto se
  quisermos atrair paciente solo no futuro. É reversível (basta
  trocar o ramo do `check`), mas é decisão a ser revisitada antes
  de campanha de aquisição focada em paciente.
- Toda chamada nova à LLM precisa lembrar de chamar `check` e
  `record_usage`. Esquecimento = bypass de gate. Mitigação: lint
  rule ou wrapper que falha se LLM é chamada sem audit + counter.
  Não no MVP, mas anotado.
