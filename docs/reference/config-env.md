# Config And Environment Reference

This page lists current mainline configuration and environment variables used by
FinHarness. It is a reference, not setup instructions.

Never commit real secrets. Do not print or paste credentials into docs, receipts,
reviews, or chat.

## Local Template

The repository includes `.env.example` with non-secret local configuration
placeholders. Copy only the values you need into a private ignored env file.

Broker credential templates from the archived live-trading experiments are not
mainline configuration. If you inspect that archive, keep credentials outside the
repo and do not reintroduce broker env vars into current docs or Taskfile tasks.

## Variables

| Variable | Used by | Purpose | Safety note |
| --- | --- | --- | --- |
| `FINHARNESS_STATE_CORE_DB_PATH` | `finharness.statecore.store`, runtime scripts | Override the State Core SQLite path. | Changes the queryable state mirror. |
| `FINHARNESS_RECEIPT_ROOT` | `finharness.config`, runtime scripts | Override receipt root. | Receipt files are evidence roots; preserve/back up deliberately. |
| `FINHARNESS_BACKUP_ROOT` | `finharness.config`, `scripts/backup.py` | Override backup destination. | Do not point at a transient or shared secret path. |
| `FINHARNESS_BROKER_KEYRING_SERVICE` | `finharness.config` | OS keyring service name for future broker-key reads. | Keyring only; no plaintext repo files. |
| `FINHARNESS_BROKER_KEYRING_USERNAME` | `finharness.config` | OS keyring username for future broker-key reads. | Keyring only; no plaintext repo files. |
| `FINHARNESS_LOG_JSON` | `finharness.config`, runtime logging | Toggle JSON logging. | Logs must not contain secrets. |
| `FINHARNESS_AUTHORIZATION_REGISTRY_PATH` | `finharness.authorization` | Optional authorization registry override. | Registry is policy/config, not a credential store. |
| `FINHARNESS_RESTRICTED_SYMBOLS_PATH` | `finharness.restricted_symbols` | Optional restricted-symbol registry override. | Research-symbol restrictions only. |
| `OPENAI_API_KEY` | `task agent:run`, agent scripts | Enables the real OpenAI agent runner. | Secret; optional for most local paths. |
| `PYTHONPATH` | `Taskfile.yml` | Compatibility fallback for scripts that execute source paths directly; normal `uv` commands import the editable installed package. | Project task config. |
| `PROMPTFOO_DISABLE_TELEMETRY` | `Taskfile.yml`, agent eval helpers | Disables promptfoo telemetry in task runs. | Project task config. |
| `PROMPTFOO_DISABLE_UPDATE` | `Taskfile.yml`, agent eval helpers | Disables promptfoo update checks. | Project task config. |

## Mainline Boundary

Current mainline has no Taskfile entry for live broker execution. Environment
variables alone must never create execution authority. If a future mainline
capability needs broker or venue credentials, it must be introduced through a
new proposal/ADR, explicit gates, receipt handling, and documentation updates in
the same PR.
