---

## Escopo do MVP

### Dentro do MVP
1. Auth OAuth Google
2. Perfis de psicólogo e paciente
3. Vínculo via código de convite (fluxo dos dois lados)
4. Registro de humor: escala emocional + texto + marcação de privacidade
5. Modo individual (paciente sem psicólogo)
6. Visualização do psicólogo: lista de pacientes + linha do tempo de registros compartilhados
7. Consentimento granular LGPD
8. Pipeline de pseudonimização (spaCy + Presidio)
9. Celery + Redis para processamento assíncrono
10. Análise por Claude: resumo semanal e briefing pré-sessão para o psicólogo
11. Devolutiva de padrões para o paciente (modo autoconhecimento)

### Fora do MVP (entra em v2+)
- Áudio e transcrição (Whisper)
- Escalas clínicas (PHQ-9, GAD-7)
- Sessões agendadas + anotações clínicas estruturadas
- Sistema de alertas automáticos
- Prescrição de atividades terapêuticas
- App mobile React Native (web responsivo no MVP)
- 2FA (psicólogo entra com Google só, no MVP)
- Login Apple
- Modo de apoio em crise interativo (link estático para CVV resolve)

---

## Decisões Técnicas Documentadas (ADRs sugeridos)

Lista inicial de decisões para documentar em `docs/adr/`:

1. Por que Django em vez de Flask
2. Por que PostgreSQL em vez de MySQL
3. Por que HTMX para web em vez de React/Next.js separado
4. Por que React Native em vez de PWA para mobile (v2)
5. Por que OAuth social em vez de email/senha
6. Por que Claude para análise clínica em vez de GPT-4
7. Por que pseudonimização em vez de tentativa de anonimização real
8. Por que Celery em vez de processar IA de forma síncrona
9. Por que Cloudflare R2 em vez de AWS S3 (v2)
10. Por que sessões server-side em vez de JWT
11. Por que Python 3.11 em vez de 3.12

Cada ADR é um arquivo markdown curto (1 página) explicando: contexto, decisão, alternativas consideradas, consequências.

---

## Considerações Finais

Esta especificação técnica complementa o documento de visão do produto (`docs/vision.md`). Juntos, eles formam a base do projeto MoodTrack e devem ser usados como contexto fundacional em todas as decisões e desenvolvimentos futuros. Qualquer alteração significativa nesta stack deve ser registrada em um ADR antes da implementação.