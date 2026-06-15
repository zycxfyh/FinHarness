# How To Promote A Lesson Draft Into A Rule Change

Use this when a human has reviewed a lesson draft and wants to record a
traceable rule, threshold, checklist, allowlist, or prompt-template change.

AI may draft lessons. A human promotes them.

## Draft Lessons

```bash
task lessons:draft
```

Optional LLM-assisted drafting:

```bash
task lessons:draft -- --llm
```

This writes:

```text
docs/lessons/drafts/<date>-<draft_id>.md
data/receipts/lessons/<draft_id>.json
```

## Review Before Promotion

Before promoting, check:

- the draft has real receipt refs;
- the proposed rule changes future behavior;
- the rationale is written in human language;
- the change target is specific;
- the change does not weaken a safety boundary.

## Promote

```bash
task lessons:promote -- \
  --draft-receipt data/receipts/lessons/<draft_id>.json \
  --rule-target guard.hard_stop_consecutive_losses \
  --change-kind threshold \
  --old-value 3 \
  --new-value 2 \
  --rationale "Human-reviewed lesson: tighten after repeated loss clusters." \
  --attester "your-name" \
  --lesson-doc docs/lessons/<date>-<slug>.md
```

Allowed `--change-kind` values:

```text
threshold
checklist
allowlist
prompt_template
```

## Audit

```bash
task rules:audit
```

The audit must report:

```json
{
  "b4_lineage_ok": true
}
```

## Safety Boundary

- A draft is not a rule.
- A rule change without lesson and receipt refs is refused.
- A human attester is required.
- Promotion records lineage; it does not prove the new rule is optimal.
