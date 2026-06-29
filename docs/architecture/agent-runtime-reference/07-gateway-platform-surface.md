# 07 Gateway / Platform Surface

Hermes treats each external entry point as a platform surface with its own session context, authorization, formatting rules, delivery capability, and data exposure limits.

```text
User -> Platform Adapter -> Gateway Runner -> Agent Runtime
```

The useful pattern for FinHarness is not “add Slack/Telegram/etc”. It is: every entry point must declare what kind of session it creates.

## Hermes Pattern

Hermes platform entries are registry objects, not `if/elif` branches. They include adapter factory, availability checks, config validation, required environment, message length, PII policy, allowed users, platform hints, async delivery, cron delivery, and standalone sender support.

Hermes also keeps gateway session state in task-local context, not process-global environment variables. That prevents concurrent messages from different users, chats, or threads from polluting each other.

## FinHarness Mapping

FinHarness surfaces should eventually be modeled explicitly:

| Surface | Default posture |
| --- | --- |
| CLI | local, explicit operator, can show bounded diagnostics |
| Cockpit | authenticated review UI, selected scope only |
| API | strict schema, no implicit async callback |
| Batch | job record and receipt, no interactive prompt |
| Promptfoo/tests | synthetic or fixture-only data |

Potential `CapitalSurfaceEntry` fields:

- `name`
- `profile_default`
- `supports_async_delivery`
- `can_write_review_objects`
- `can_show_sensitive_data`
- `max_payload_chars`
- `pii_safe`
- `prompt_hint`

## Session Context

FinHarness should avoid global mutable session state for:

- `active_user`
- `active_profile`
- `selected_portfolio`
- `selected_proposal_id`
- `selected_account_scope`
- `current_surface`
- `session_id`
- `state_snapshot_id`
- `receipt_root`

If Cockpit/API/batch sessions become concurrent, one user’s selected proposal must not affect another user’s review.

## Async Delivery Contract

A surface must not promise background completion if it cannot deliver it.

| Surface | Async completion |
| --- | --- |
| CLI interactive | possible if process remains alive |
| Cockpit websocket | possible |
| Stateless API | no; use job polling or receipt lookup |
| Batch queue | yes, through job record |
| Cron | yes, only with configured delivery channel |

This matters for future long-running simulation, imports, and queue checks.

## PII / Attachment Rules

Financial surfaces should control:

- account amount visibility;
- account identifier redaction;
- receipt raw payload access;
- export redaction;
- source attachment size;
- document/PDF/media ingestion limits.

LLM response is not an unrestricted data export.
