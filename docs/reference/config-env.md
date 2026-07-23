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
| `FINHARNESS_BACKUP_ROOT` | `finharness.config`, backup commands | Override backup destination; it may be an off-device mounted path. | Use durable storage with independently monitored capacity. |
| `FINHARNESS_BACKUP_MIN_FREE_BYTES` | `finharness.backup` | Minimum free-space reserve required after the conservative input-size estimate. Default: 512 MiB. | Backup creation fails before writing artifacts when the threshold is not met. |
| `FINHARNESS_BACKUP_RETENTION_COUNT` | `finharness.backup` | Minimum number of newest verified backups protected from retention. Default: 7. | Must be at least 1; the newest valid backup is always protected. |
| `FINHARNESS_BACKUP_RETENTION_DAYS` | `finharness.backup` | Age after which verified backups beyond the protected count become prune candidates. Default: 30. | Pruning is dry-run unless `--apply` is explicit; `.legal-hold` backups are excluded. |
| `FINHARNESS_BROKER_KEYRING_SERVICE` | `finharness.config` | OS keyring service name for future broker-key reads. | Keyring only; no plaintext repo files. |
| `FINHARNESS_BROKER_KEYRING_USERNAME` | `finharness.config` | OS keyring username for future broker-key reads. | Keyring only; no plaintext repo files. |
| `FINHARNESS_LOG_JSON` | `finharness.config`, runtime logging | Toggle JSON logging. | Logs must not contain secrets. |
| `FINHARNESS_AUTHORIZATION_REGISTRY_PATH` | `finharness.authorization` | Optional authorization registry override. | Registry is policy/config, not a credential store. |
| `FINHARNESS_RESTRICTED_SYMBOLS_PATH` | `finharness.restricted_symbols` | Optional restricted-symbol registry override. | Research-symbol restrictions only. |
| `OPENAI_API_KEY` | `task agent:run`, agent scripts | Enables the bounded OpenAI-compatible model review. | Secret; optional; never written to receipts. |
| `OPENAI_BASE_URL` | `task agent:run`, model audit port | Selects the OpenAI-compatible API endpoint; DeepSeek uses `https://api.deepseek.com`. | Endpoint only, not authority. |
| `FINHARNESS_AGENT_MODEL` | `task agent:run`, model audit port | Selects the configured model; current DeepSeek choice is `deepseek-v4-pro`. | Model output remains subordinate to deterministic invariants. |
| `UV_LOCKED` | `Taskfile.yml` | Makes project task invocations fail when `uv.lock` is stale instead of updating it implicitly. | Dependency changes must update the lockfile deliberately outside the verification tasks. |
| `PROMPTFOO_DISABLE_TELEMETRY` | `Taskfile.yml`, agent eval helpers | Disables promptfoo telemetry in task runs. | Project task config. |
| `PROMPTFOO_DISABLE_UPDATE` | `Taskfile.yml`, agent eval helpers | Disables promptfoo update checks. | Project task config. |

## Mainline Boundary

Current mainline has no Taskfile entry for live broker execution. Environment
variables alone must never create execution authority. If a future mainline
capability needs broker or venue credentials, it must be introduced through a
new proposal/ADR, explicit gates, receipt handling, and documentation updates in
the same PR.
