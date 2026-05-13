# ADR 0012 — Billing via Stripe Subscriptions

**Status:** aceito
**Data:** 2026-05-13

## Contexto

A ADR 0010 definiu os planos do profissional (Básico/Pro/Premium) e o gate
de IA. A ADR 0011 fechou o custo real em reais por chamada. Em ambas, a
mudança de plano é manual via admin — não há fluxo do profissional pagar e
ganhar acesso. Sem isso, o gate de custo é teoria: ninguém paga, ninguém
muda de plano, a IA fica trancada em "admin libera".

Este ADR define **como o profissional vira pagante** e **como o pagamento
confirma a mudança de plano em sistema**.

## Decisão

### Provedor: Stripe

Em test mode no MVP, com migração para credenciais reais quando houver
primeiro usuário pagante. Stripe foi escolhido por:

- SDK Python maduro (`stripe` no PyPI, documentação excelente)
- Webhook signature verification nativo (segurança fail-closed)
- Stripe Checkout (hosted) e Customer Portal (hosted) cortam superfície de
  PCI e UI que teríamos que construir
- Suporte a recorrência mensal nativo (Subscriptions)

**Trade-off:** Stripe não tem PIX nativo no Brasil. Psicólogo BR prefere
PIX/boleto. Decisão consciente: começar com cartão (BR funciona via Stripe
em BRL), e adicionar Mercado Pago/PIX como segunda integração quando houver
volume justificando. Não bloqueia o MVP.

### Modelo: Subscription, não one-time

Planos são mensais (R$50/R$200). Stripe Subscriptions tratam:
- Cobrança recorrente automática
- Retry de falha de pagamento
- Pro-rating em upgrade/downgrade mid-cycle
- Cancelamento com acesso até fim do período

### Stripe Checkout (hosted), não Elements

Profissional clica em "Assinar Pro" → redireciona pra `checkout.stripe.com`
→ paga → volta pra MoodTrack. Vantagens:

- **PCI minimizado:** nenhum dado de cartão toca o servidor MoodTrack
- **Implementação enxuta:** UI de cobrança é Stripe; nós só criamos a Session
- **Trade-off:** UX menos integrada (redirect para domínio externo). Aceitável
  pro MVP — usuário psicólogo paga 1x por mês, não é hot path

### Customer Portal (hosted) pra gerenciamento

Cancelar, trocar de plano, atualizar cartão, ver invoices — tudo no portal
hospedado da Stripe. Mesma lógica: pouco código nosso, UX consistente.

### Webhook é a única fonte de verdade

`HealthcareProvider.plan` **só** muda via webhook. Nenhuma view escreve
o campo diretamente em resposta a clique do usuário (mesmo após "sucesso"
no Checkout, a view de retorno NÃO promove o plano — ela apenas mostra
"estamos processando").

Razão (CLAUDE.md regra 5 — fail-closed):
- Usuário pode acessar URL de sucesso manualmente sem ter pago
- Pagamento pode falhar entre Checkout e nossa URL de retorno
- Subscription pode ser cancelada por chargeback retroativo

Stripe avisa o estado real via webhook events com signature verificada.
Confiar no webhook = confiar no que Stripe assina como verdade.

### Schema

Em `HealthcareProvider` (apps/accounts), 2 campos novos:

```python
stripe_customer_id = models.CharField(max_length=64, blank=True, db_index=True)
stripe_subscription_id = models.CharField(max_length=64, blank=True)
```

Lazy: customer é criado na primeira tentativa de checkout (não no signup).
Mantém o signup leve e não chama Stripe pra quem nunca tentou assinar.

Em novo app `apps/billing`:

```python
class WebhookEvent(models.Model):
    """Log idempotente de eventos recebidos da Stripe.

    `event_id` único — Stripe pode reenviar o mesmo evento; lookup garante
    processamento exatamente uma vez.
    """
    event_id = models.CharField(max_length=128, unique=True)
    event_type = models.CharField(max_length=64)
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)  # se processing falhou
```

### Eventos tratados

| Event | Ação |
|---|---|
| `checkout.session.completed` | Grava `subscription_id` no provider, atualiza `plan` baseado no `price.id` |
| `customer.subscription.updated` | Ajusta `plan` se o `price.id` mudou (upgrade/downgrade pelo portal) |
| `customer.subscription.deleted` | Reset `plan = BASIC`, limpa `subscription_id` |
| Outros | Log e ignora |

### Segurança

- **Webhook signature verification obrigatória** (`stripe.Webhook.construct_event`).
  Falha → 400, NÃO processa. Sem isso, qualquer um pode POSTar promovendo
  plano (CLAUDE.md regra 5).
- **CSRF exempt apenas no endpoint do webhook.** Stripe não envia token CSRF;
  signature é o auth.
- **Idempotência via `WebhookEvent.event_id` unique.** Reentrega de evento
  retorna 200 sem reprocessar.
- **Audit log** em toda mudança de plano (`apps.audit.log_event` com
  `actor=None` porque o "ator" é o Stripe).
- **STRIPE_API_KEY e STRIPE_WEBHOOK_SECRET via env vars** — nunca commitados.

### Encapsulamento (`apps/billing/stripe_client.py`)

Wrapper fino sobre `stripe` SDK, espelhando o padrão do
`apps/ai/anthropic_client.py`:

- Lazy init (não levanta na ausência de chave em tempo de import)
- Erros tratáveis (`StripeBillingError`)
- Métodos: `get_or_create_customer(provider)`, `create_checkout_session(...)`,
  `create_portal_session(...)`, `verify_webhook(payload, signature)`

Permite mock em testes sem precisar do `stripe-mock` real.

## Alternativas consideradas

- **Mercado Pago primeiro.** Brasileiro, suporta PIX. SDK Python menos
  polido, webhook formato diferente. Descartado pra primeira iteração; fica
  como segundo provider no roadmap depois que houver tração.
- **Stripe Elements (embedded form).** UX mais integrada, mas exige cuidado
  com PCI (form de cartão dentro do nosso domínio, mesmo que via iframe).
  YAGNI pro MVP — Checkout hosted funciona.
- **One-time charges em vez de subscriptions.** Profissional pagaria mês a mês
  manualmente. Atrito alto, churn passivo (esquece de pagar). Descartado.
- **Promover plan diretamente no callback de sucesso.** Mais simples, mas
  inseguro (URL pode ser visitada sem ter pago). Webhook-as-truth não é
  negociável.
- **Manter `apps/billing` dentro de `apps/accounts`.** Misturaria modelo de
  domínio (perfil profissional) com integração externa de cobrança.
  Separação ajuda em troca de provider no futuro.

## Consequências

**Positivas:**
- Plano profissional → IA habilitada vira fluxo end-to-end automatizado.
- ADR 0010 e 0011 deixam de ser parcialmente abstratas — gate de custo
  finalmente tem o "outro lado" (alguém pagando).
- UI de cobrança / portal de gerenciamento é zero código nosso.
- Migrar pra Mercado Pago (adicionar PIX) depois é trocar/adicionar
  `stripe_client.py` por implementação análoga; o gate em `apps.ai.access`
  não muda.

**Negativas:**
- Dependência externa nova com superfície de segurança (webhook).
  Mitigação: signature verification + tabela idempotente + audit.
- Test mode permite todo o fluxo de dev sem cobrança real, mas migração pra
  produção exige passos manuais (verificação de conta Stripe, configuração
  de produtos/preços, troca de chaves no .env). Documentar em README.
- Stripe cobra ~3.99% + R$0.39 por transação. R$50/mês paga ~R$1.99 +
  R$0.39 ≈ R$2.38 de fee. Aceitável para MVP.
- Profissional brasileiro pode estranhar pagar via "Stripe" em vez de PIX.
  Aceito como atrito conhecido até segunda integração.
