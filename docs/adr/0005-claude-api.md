# ADR 0005 — Claude API (Anthropic) para análise clínica de IA

**Status:** aceito
**Data:** 2026-05-08

## Contexto

A camada de IA do MoodTrack tem responsabilidades bem definidas (ver
`docs/vision.md`):

1. Resumo semanal dos registros do paciente.
2. Briefing pré-sessão para o psicólogo.
3. Identificação de temas recorrentes e correlações.
4. (V2) Detecção de sinais de risco e alertas.

Os dados processados, mesmo após pseudonimização (ver ADR futuro sobre
pseudonimização), seguem sendo profundamente íntimos. Os requisitos não
negociáveis para o provedor de LLM:

- **Zero Data Retention (ZDR) configurável** — dados enviados não podem ser
  retidos pelo provedor após a resposta, e não podem ser usados para treinamento.
- **Qualidade de português brasileiro** suficiente para compreender registros
  emocionais coloquiais, gírias, diminuitivos, sintaxe natural de paciente.
- **Postura ética explícita** do fornecedor — ainda que isso não seja
  contrato, o produto se beneficia de fornecedor que publicamente investe
  em alinhamento e segurança.
- **Acesso via API estável** com SDK Python oficial.
- **Suporte a long context** para resumos de várias semanas sem fragmentar
  artificialmente.

## Decisão

Adotar **Anthropic Claude** via API oficial (`anthropic` SDK Python) como
provedor único de LLM no MVP. **Zero Data Retention deve estar habilitado na
conta Anthropic antes de qualquer chamada com dados reais** — esse status é
documentado no README e validado em onboarding de ambiente.

A regra de não enviar dados não-pseudonimizados (CLAUDE.md, regra 1) vale
independente do provedor.

## Alternativas consideradas

- **OpenAI GPT-4 / GPT-5.** Excelente em PT-BR, ZDR disponível em planos
  enterprise. Descartado por preferência clara em alinhamento e postura ética
  pública da Anthropic, e por evitar lock-in dual. Pode entrar como segundo
  provedor se latência ou disponibilidade da Anthropic forçar fallback.
- **Modelos open-source self-hosted (Llama 3, Mistral, Gemma).**
  Atrativo do ponto de vista de privacidade absoluta — nada sai da nossa infra.
  Descartado para o MVP por:
  - Qualidade clínica em PT-BR ainda inferior em tarefas de síntese
    interpretativa.
  - Operação de inferência (GPU, escalabilidade, monitoramento) não compensa
    com o time atual.
  - Custo total (GPUs idle vs. pay-per-token) só fecha em volume alto.
  Reavaliar quando volume de paciente justificar e/ou regulação exigir
  processamento on-prem.
- **Google Gemini.** Capaz, mas postura sobre uso de dados de API menos clara
  historicamente; menos prioridade.

## Consequências

**Positivas:**
- ZDR contratualmente disponível e documentável para auditoria interna e
  resposta a titulares (LGPD).
- Qualidade alta em PT-BR e em raciocínio interpretativo — adequado a
  síntese clínica de apoio (não diagnóstico, conforme CLAUDE.md regra 13).
- SDK Python oficial estável; versionamento de modelo explícito (podemos
  pinar `claude-opus-4-7` ou `claude-sonnet-4-6` por feature).
- Long context permite briefings com várias semanas de registros sem
  fragmentação artificial.
- Postura ética da Anthropic alinha com o posicionamento do produto.

**Negativas:**
- Vendor lock-in. Mitigação: encapsular toda chamada em `apps/ai/` por trás
  de uma interface interna (`generate_summary`, `generate_briefing`, etc.) —
  trocar de provedor envolve trocar uma camada, não cada call site.
- Custo por token. Mitigação: cache de prompts repetitivos (system prompts,
  contexto de paciente) usando prompt caching da Anthropic; usar Haiku/Sonnet
  para tarefas simples e Opus apenas onde valor clínico justificar.
- Disponibilidade da API afeta features de IA. Resumos e briefings rodam em
  Celery (assíncrono), então uma falha temporária degrada a feature mas não
  derruba o produto.
- Dependência de internet para qualquer geração — esperado em produto cloud,
  mas registrado.
