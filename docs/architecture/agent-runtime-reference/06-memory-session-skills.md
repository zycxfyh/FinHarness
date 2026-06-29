# 06 Memory / Session / Skills

Hermes splits long-context support into three different mechanisms:

| Mechanism | What it is | What it is not |
| --- | --- | --- |
| Memory | Durable user/project preferences or facts | Current source evidence |
| Session Search | Historical conversation recall | Proof of current state |
| Skills | Procedures and workflow instructions | Runtime authority |

FinHarness should keep these categories separate because finance governance depends on evidence lineage.

## Memory

Memory is useful for durable preferences:

- preferred language;
- risk communication style;
- recurring review habits;
- user-stated constraints that should be rechecked;
- stable product preferences.

Memory should not store or replace:

- current portfolio state;
- proposal status;
- receipt contents;
- PR status;
- raw logs;
- secrets;
- executable authorization.

Hermes freezes memory snapshots per session. That is a useful safety pattern: a memory write can update durable storage, but the current session should not silently gain new authority from it.

## Session Search

Session search can answer “what did we discuss before?” It should not answer “what is true now?”

FinHarness should treat session history as:

- historical conversation context;
- a pointer to possible decisions;
- a source for finding related docs or receipts.

It should not be treated as:

- current evidence;
- current state;
- approval;
- receipt.

## Skills

Skills are procedures. They should be progressively disclosed: load only the instruction needed for the current task.

For FinHarness, skills may help with:

- review workflow;
- documentation governance;
- evidence audit;
- security review;
- release preflight;
- proposal triage.

But a skill cannot override runtime policy. If a skill says to approve, execute, or rewrite a receipt, the Agent runtime must still enforce FinHarness authority boundaries.

## FinHarness Context Taxonomy

| Term | Source of truth |
| --- | --- |
| User Memory | durable preference, never current capital state |
| IPS / Policy | user policy records and policy checks |
| StateCore | local state mirror and receipts |
| Receipt | evidence of a recorded event |
| Proposal | governed review object, not execution |
| Attestation | human decision record, not broker action |
| Session Search | historical conversation recall |
| Skill | procedure for how to work |
| Lesson | promoted learning with lineage |

## Runtime Rule

Use this ordering when Agent output depends on evidence:

```text
current source/state/receipt > proposal/review event > policy record
> session history > memory preference > model summary
```

If an answer cannot reach current evidence, it should say so plainly and stay in explanation mode.
