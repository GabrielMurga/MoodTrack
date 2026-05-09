# ADR 0008 — Cliente Anthropic, ZDR, e gates de segurança

**Status:** aceito
**Data:** 2026-05-08

## Contexto

ADR 0005 já fixou Claude (Anthropic API) como provedor único de LLM no
MVP. Esta ADR complementa com decisões operacionais:

- Como invocar a API (encapsulamento, escolha de modelo, caching).
- Como garantir que **nenhuma chamada acontece sem ZDR confirmado**
  (CLAUDE.md regra 14).
- Estratégia de tarefa síncrona vs assíncrona.

## Decisão

### Encapsulamento

Toda interação com a Anthropic SDK acontece em
`apps/ai/anthropic_client.py`. Views e tarefas chamam métodos do
client; nunca importam `anthropic` diretamente.

Isso atende dois objetivos:
- **Vendor lock-in mitigado**: trocar de provedor envolve mexer só nesta
  camada (ver ADR 0005, "Vendor lock-in").
- **Mockabilidade em testes**: client tem interface clara, fácil
  substituir por dublê.

### Modelo default e caching

- **Default**: `claude-sonnet-4-6`. Boa qualidade clínica em PT-BR,
  custo razoável. Opus 4.7 reservado para saídas que pedem mais
  raciocínio (não usado nesta fatia).
- **Prompt caching ativado** nos system prompts. Os system prompts
  são longos (regras de não-diagnóstico, formato de saída, instruções
  sobre placeholders) e repetem entre chamadas — caching corta custo
  e latência.

### Gate de ZDR em runtime

Antes de qualquer chamada à API:

```python
if not env.bool("ANTHROPIC_ZDR_CONFIRMED", default=False):
    raise AnthropicClientError(
        "Chamadas à Anthropic API estão bloqueadas até "
        "ANTHROPIC_ZDR_CONFIRMED=true ser definido. "
        "Confirme ZDR em console.anthropic.com antes de habilitar."
    )
```

Funciona como cinto de segurança: a flag tem que ser definida
**explicitamente** após você confirmar no painel da Anthropic. Se a
flag não estiver lá, o sistema não chama a API. Em dev sem chave, a
view mostra erro amigável; em prod sem flag, falha rápido.

### Sync vs async

Esta fatia faz **chamadas síncronas em-view**. Bloqueia a request por
3-10 segundos. Aceitável pelo escopo: geração on-demand, baixa
frequência, baixa concorrência.

Quando entrar:
- Resumos semanais agendados → precisa Celery beat.
- Volume alto → precisa fila.
- Streaming de resposta → precisa async ou WebSocket.

Cada um vira fatia/ADR própria.

### Sem ANTHROPIC_API_KEY em dev

O sistema continua funcionando — pseudonimização roda, modelos
retornam erro amigável na view ("IA não configurada — administrador
precisa setar ANTHROPIC_API_KEY"). Não 500.

## Alternativas consideradas

- **Chamar Anthropic SDK direto na view**: mais rápido de escrever,
  mas espalha vendor lock-in pelo codebase. Descartado.
- **Sem gate de ZDR, confiar em "sempre lembrar de configurar"**:
  inviável. Erro humano clínico = vazamento de PII pra LLM. ZDR gate
  é cinto de segurança simples e barato.
- **Async com Celery desde já**: complica esta fatia (precisa Redis
  rodando, supervisor, configuração). Sync resolve até a próxima fatia
  começar.

## Consequências

**Positivas:**
- API key + ZDR explícitas em env, com fail-fast se ausente.
- Trocar provedor = mudar uma camada.
- Caching ativo desde o dia 1 → custo baixo.
- Modelo configurável por chamada (default Sonnet, override quando
  precisar Opus).

**Negativas:**
- Sync em-view tem UX ruim em conexão lenta. Aceito por agora.
- Sem Celery, sem agendamento. Resumos semanais ficam manuais.
- Caching da Anthropic exige system prompt estável; mudar prompts
  invalida cache.
