# Manage Governance Inventories

Some inventory fields are observations and should not depend on memory. The
repository derives dependency requirements, declared groups, imported modules,
and Python consumer paths from `pyproject.toml` and maintained source roots. It
also derives the attestation inventory summary from its reviewed consumer
records.

Check without modifying files:

```bash
task governance:inventory
```

Repair derived drift in one step:

```bash
task governance:inventory:update
```

The update is deterministic and idempotent. It does not invent dependency
recommendations, task ownership, rationale, confidence, attestation risk, or
migration disposition. A new dependency therefore fails with its exact name
until a reviewer adds those policy fields. Paper-validation consumer relations
and deletion gates also remain reviewed judgments; check mode reports the exact
unregistered or stale path but does not synthesize a migration decision.

`task governance:check` includes the read-only drift check. CI never invokes the
update mode.
