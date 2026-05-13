# ADR 0009 — Profissional de saúde unificado (psicólogo + psiquiatra)

**Status:** aceito
**Data:** 2026-05-09

## Contexto

O MVP definiu psicólogo como único perfil profissional. A direção do
produto mudou: psiquiatras entram agora, com a **mesma mecânica de
plataforma** (vínculo paciente-profissional, timeline, anotações
clínicas, planos, cotas de IA, audit log). A diferença real entre os
dois perfis é estreita mas significativa:

- **Registro profissional**: psicólogo tem CRP (Conselho Regional de
  Psicologia), psiquiatra tem CRM (Conselho Regional de Medicina).
- **Capacidade de prescrição**: psiquiatra é médico e prescreve
  medicação; psicólogo não.
- **Implicações regulatórias**: psicólogo é regulado pelo CFP/CRP,
  psiquiatra pelo CFM/CRM. Receita digital, sigilo médico estrito,
  obrigações de prontuário diferentes (a maioria delas fora do escopo
  do MVP, mas o modelo de dados precisa permitir essa divergência sem
  refactor doloroso depois).

Hoje existe `apps/accounts/models.py::PsychologistProfile`
(OneToOne com User, com `crp_number`, `bio`). Está referenciado por 16
arquivos (apps `bonds`, `journal`, `ai`, testes, factories, admin,
seed, migrations). Qualquer mudança de modelagem afeta todos esses
pontos.

A pergunta é como acomodar psiquiatra:

1. Criar `PsychiatristProfile` paralelo a `PsychologistProfile`,
   duplicando a estrutura (vínculo, planos, cotas).
2. Generalizar para `HealthcareProvider` com campo `kind` enum
   (`psychologist`, `psychiatrist`).
3. Manter `PsychologistProfile` e adicionar flag `is_psychiatrist`
   (gambiarra: nome do model passa a mentir sobre o conteúdo).

## Decisão

Adotar **opção 2: `HealthcareProvider` unificado** com campo `kind`.

### Modelagem

```python
class ProviderKind(models.TextChoices):
    PSYCHOLOGIST = "psychologist", _("Psicólogo")
    PSYCHIATRIST = "psychiatrist", _("Psiquiatra")


class HealthcareProvider(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="provider_profile",
    )
    kind = models.CharField(
        max_length=20,
        choices=ProviderKind.choices,
    )
    # CRP preenchido se kind=psychologist; CRM se kind=psychiatrist.
    # Validação em clean() conforme kind. Free-text por enquanto
    # (validação real contra base do CFP/CFM fica para iteração futura,
    # mantendo o que já valia para CRP).
    crp_number = models.CharField(max_length=20, blank=True)
    crm_number = models.CharField(max_length=20, blank=True)

    bio = models.TextField(blank=True)
    plan = models.CharField(...)  # adicionado em ADR 0010

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

`clean()` impõe consistência entre `kind` e o número de registro
(`psychologist` exige CRP preenchido, `psychiatrist` exige CRM, e o
campo "do outro" deve permanecer vazio).

### Capacidade de prescrição

A capacidade de prescrição é **derivada de `kind`**, não armazenada
como flag separada:

```python
@property
def can_prescribe(self) -> bool:
    return self.kind == ProviderKind.PSYCHIATRIST
```

Modelos que registram prescrição (definidos em fatia futura para o
bloco "Resumo + Medicações") usam `can_prescribe` em validação
fail-closed (CLAUDE.md regra 5). Um psicólogo tentando criar um
registro de prescrição é negado em nível de model, não só de view.

### Vínculo paciente-profissional

`apps/bonds/` hoje liga paciente a `PsychologistProfile`. Passa a
ligar a `HealthcareProvider` independente do `kind`. Toda a state
machine de convite (CLAUDE.md regra 4) permanece igual — a confirmação
dos dois lados é semântica de plataforma, não específica de psicólogo.

### Migração

Renomeação de model em Django **não é destrutiva** se feita via
`migrations.RenameModel`. O caminho:

1. Renomear `PsychologistProfile` → `HealthcareProvider` em models.
2. Atualizar todas as 16 referências (FKs, imports, factories, testes,
   admin, seed, templates).
3. Migration gerada inclui `RenameModel` + `AddField` (`kind`,
   `crm_number`). Postgres faz `ALTER TABLE RENAME` — zero perda de
   dados.
4. `kind` recebe default `psychologist` na migration de dados, já que
   todo registro existente é psicólogo.
5. `related_name` muda de `psychologist_profile` para `provider_profile`
   no User. Property `is_psychologist` em `User` passa a checar
   `hasattr(user, "provider_profile") and user.provider_profile.kind ==
   ProviderKind.PSYCHOLOGIST`. Nova property `is_psychiatrist` segue o
   mesmo padrão.

CLAUDE.md classifica migration destrutiva como "drop column, drop
table". Rename de tabela e adição de coluna **não** se enquadram —
ainda assim, esta ADR documenta a mudança porque afeta múltiplos apps.

### Compatibilidade reversa

Não há. Psicólogos cadastrados continuam funcionando sob o novo
modelo (kind=psychologist, related_name novo); nenhuma API pública é
quebrada porque o produto ainda não tem usuários reais externos. Não
mantemos alias `PsychologistProfile = HealthcareProvider` — o nome
antigo desaparece pra evitar confusão (CLAUDE.md: "Avoid
backwards-compatibility hacks").

## Alternativas consideradas

- **Opção 1: `PsychiatristProfile` separado.** Duplica vínculo, planos,
  cota, audit. Cada feature compartilhada precisaria ser implementada
  duas vezes ou abstraída atrás de uma interface comum (que é
  basicamente reinventar o `HealthcareProvider`). Descartado.
- **Opção 3: flag `is_psychiatrist` em `Psychologist`.** Nome do model
  passa a mentir sobre o conteúdo; código que itera "todos os
  psicólogos" começa a precisar lembrar de filtrar a flag. Gambiarra
  com prazo de validade curto. Descartado.
- **Tabela separada `PrescriptionCapability` ligada a `Provider`.**
  Modela capacidade de prescrição como dado, não como derivação de
  `kind`. Útil se no futuro houvesse psicólogos com prerrogativa
  excepcional de prescrição (não existe no Brasil hoje). Excesso de
  flexibilidade pra um problema que não temos. Descartado pelo YAGNI.

## Consequências

**Positivas:**

- Vínculo, timeline, planos, cotas, audit funcionam em uma camada só
  pra ambos os perfis. Manutenção e features novas custam metade.
- `kind` deixa explícito no banco quem é o quê — queries que
  precisam filtrar (ex: "lista de psiquiatras pra paciente escolher")
  ficam triviais.
- Capacidade de prescrição derivada de `kind` evita estado
  inconsistente (não dá pra ter "psicólogo que prescreve").
- Adicionar um terceiro tipo de profissional no futuro
  (neuropsicólogo, terapeuta ocupacional) é só adicionar um valor ao
  enum + campo de registro correspondente.

**Negativas:**

- Migration toca 16 arquivos. Rename + atualização de FKs + ajuste de
  `related_name` exige cuidado em testes pra não quebrar nada
  silenciosamente. Mitigação: rodar suite completa após cada passo.
- `crp_number` e `crm_number` ficam ambos no model, com só um
  preenchido por vez. É um pouco "esparso" mas evita criar tabela
  filha por algo tão pequeno. `clean()` garante consistência.
- Validação real de CRP/CRM contra base oficial continua sendo free-
  text por enquanto. Não é regressão (já era assim para CRP), mas a
  superfície agora é maior.
- Templates e views que mostram "Psicólogo: Fulano" precisam virar
  algo como "{{ provider.get_kind_display }}: {{ provider.user.full_name }}"
  pra não estar incorreto pra psiquiatra.
