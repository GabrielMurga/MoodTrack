# ADR 0007 — Pseudonimização antes de chamadas à LLM

**Status:** aceito
**Data:** 2026-05-08

## Contexto

CLAUDE.md regra 1 estabelece que **nenhum dado de paciente vai pra LLM
externa sem passar pelo pipeline de pseudonimização**. A regra cita
spaCy (`pt_core_news_lg`) + Microsoft Presidio como ferramentas.

Os dados que podem chegar à pipeline:
- `JournalEntry.content` — texto livre, em PT-BR coloquial.
- `MoodLog` — sem texto, mas com timestamp.
- `ClinicalNote.content` — anotações do psicólogo, podem mencionar
  pessoas, locais, eventos.

Identificadores que precisam ser substituídos:
- Nomes próprios (PERSON / pessoas mencionadas pelo paciente)
- Locais (cidades, bairros, países, instituições)
- Datas específicas (ex.: "no dia 12 de março de 2026")
- Telefones, emails, CPF
- Eventualmente: nomes de empresas, cargos específicos

## Decisão

Adotar **pseudonimização baseada em spaCy `pt_core_news_lg` + regex
customizadas**, sem Presidio nesta fatia.

Estratégia:

1. **Forward**: spaCy NER detecta entidades (`PER`, `LOC`, `ORG`, `MISC`).
   Regex próprias detectam padrões estruturados (CPF, telefone, email,
   datas no formato DD/MM/YYYY). Cada entidade detectada é substituída
   por um placeholder `[KIND_N]` (`[PERSON_1]`, `[LOC_2]`, etc.).
2. **Vault**: dicionário `placeholder → original` mantido em memória
   por chamada. Não persistido.
3. **Reverse**: aplicado no resultado da LLM antes de mostrar ao usuário.

## Por que não Presidio nesta fatia

Presidio é uma biblioteca Microsoft que adiciona uma camada de "padrões
+ contexto + validação" sobre o NER. Para inglês, oferece recognizers
prontos para SSN, US zip codes, etc. Para PT-BR:

- Presidio depende de spaCy com modelo `pt_core_news_lg` (que já temos).
- Recognizers built-in pra Brasil são poucos — CPF/CNPJ não são padrão.
- A camada de validação de contexto (ex.: "número de 11 dígitos perto
  da palavra CPF") seria útil, mas exige escrever recognizers próprios
  pra ter cobertura PT-BR razoável.

Trade-off: Presidio adiciona complexidade (mais um pacote, integração
com spaCy via wrapper, configuração de recognizers) sem ganho claro
sobre uma implementação direta de spaCy NER + regex pra os tipos de
identificador que importam aqui (CPF, telefone, email, data).

Decisão: começar sem Presidio. Se surgir necessidade de detecção mais
sofisticada (validação de contexto, scoring de confiança, recognizers
customizados pra termos clínicos), trazer Presidio com ADR próprio.

## Cobertura aceita pra MVP

Pseudonimização nunca é perfeita. Casos esperados pra **passar batido**:

- Apelidos curtos sem capitalização (ex.: "minha mãe", "meu chefe")
  — não capturados como PERSON pelo NER. Estratégia compensatória:
  prompts da LLM instruem-na a tratar com cuidado nomes/relações
  mencionadas mesmo se sem nome próprio.
- Referências indiretas a locais (ex.: "lá em casa", "no trabalho")
  — não capturados como LOC. Mesma compensação via prompt.
- Nomes próprios em formatos atípicos (caps lock, com símbolos).
- Datas em formatos coloquiais ("semana passada", "naquele dia").

Cobertura estimada: **70-85%** em texto típico de paciente. Aceitável
pra MVP onde:
- Anthropic está com ZDR ativo (dados não persistidos no provedor).
- Cada chamada loga metadata mas não o conteúdo (CLAUDE.md regra 15).
- Volume é pequeno (uso individual, não broadcast).

Para produção real e escala, reavaliar com:
- Métricas reais de cobertura
- Possível adoção de Presidio com recognizers PT-BR customizados
- Possível LLM dedicada para detecção (paradoxal mas viável: modelo
  on-prem leve só pra detecção, não pra geração)

## Vault efêmero

O mapeamento `[PERSON_1] → "João Silva"` existe **apenas em memória
durante a chamada**. Não é gravado em DB, não é persistido entre
requisições.

**Por quê:**
- Reduz superfície de exposição (vault em DB = ciphertext + chave do
  mapping = problema dobrado).
- Não há necessidade prática: o vault é usado uma vez (forward → LLM
  → reverse) e descartado.
- Auditoria registra **contagem** de placeholders criados (regra 15),
  não o vault em si.

## Consequências

**Positivas:**
- Zero dependência adicional (Presidio é grande).
- Código de pseudonimização é tão pequeno que cabe num arquivo só
  (`apps/ai/pseudonymization.py`) — fácil de auditar.
- Vault efêmero = sem problema de gestão de chaves duplicada.
- Fácil de testar isoladamente: sem rede, sem DB.

**Negativas:**
- Cobertura imperfeita (documentada acima).
- spaCy `pt_core_news_lg` é 540MB — peso na imagem de prod.
- Manutenção: novos tipos de identificador (ex.: identificador de
  carteirinha de plano de saúde) viram código aqui.
- Performance: cada chamada carrega o modelo spaCy uma vez. Mitigação:
  lazy load + singleton no módulo (modelo persiste no processo).
