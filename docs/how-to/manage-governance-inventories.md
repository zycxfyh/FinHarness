# Manage Derived Dependency Inventory

The dependency consumer manifest contains a small set of source-derived fields:
requirements, dependency groups, imported modules, and Python consumer paths.
The repository derives those fields from `pyproject.toml` and maintained source
roots so they do not depend on memory.

Check without modifying files:

```bash
task governance:inventory
```

Repair derived dependency drift:

```bash
task governance:inventory:update
```

The update is deterministic and idempotent. It does not invent dependency
recommendations, task ownership, rationale, or confidence. A new dependency
therefore fails with its exact name until a maintainer records the few policy
fields that cannot be derived from source.

The same check reports paper-validation boundary drift, but it does not generate
migration judgments. `task governance:check` includes the read-only command; CI
never invokes update mode.
