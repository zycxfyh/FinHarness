# 12 Runtime Control Plane

Hermes treats configuration as a runtime authority surface. Model, provider, tools, plugins, approvals, execution environment, gateway, memory, skills, logs, and profiles all need clear ownership and recovery rules.

For FinHarness, the control plane decides which capital world the Agent is acting in.

## Hermes Pattern

Hermes separates:

- `config.yaml` for ordinary settings;
- `.env` for secrets;
- profiles as independent home directories;
- active profile state;
- install/deployment method;
- managed mode;
- corrupt config recovery;
- config read/write locking;
- clone/export exclusions;
- env writer denylist.

A broken config is not silently ignored. It is preserved, warned about, and replaced by safe defaults only where appropriate.

## FinHarness Mapping

Future FinHarness control plane should separate:

```text
capital.yaml:
  profiles
  context budgets
  review policies
  provider selection
  surface policies
  queue checks

.env / secret manager:
  API keys
  broker read-only credentials
  database URL
  encryption keys
```

Agent/UI writable surfaces must not write:

- `BROKER_WRITE_ENABLED`
- `RECEIPT_ROOT`
- `STATECORE_ROOT`
- `FINHARNESS_HOME`
- `FINHARNESS_PROFILE`
- `PYTHONPATH`
- `PATH`
- `LD_PRELOAD`

## Profile Is Isolation

A profile is not a style label. It should eventually define an isolated domain:

- config;
- StateCore;
- receipt root;
- sessions;
- artifacts;
- logs;
- lessons;
- skills;
- provider defaults.

Possible profiles:

- research;
- review-draft;
- simulation;
- paper;
- capital-readonly;
- test/synthetic.

## Review Surface Projection

Even before a full control plane exists, review surfaces should show:

- `active_profile`;
- `surface`;
- `statecore_id`;
- `receipt_root` or receipt namespace;
- `execution_allowed=false`;
- `created_by=agent` when applicable;
- `requires_human_review=true`.

This makes the UI a control-plane projection rather than ordinary generated text.

## Control Table

| Control item | Agent may change? |
| --- | --- |
| active profile | no |
| context budget | no |
| provider selection | no |
| receipt root | no |
| IPS/policy | no; may propose change |
| proposal draft | yes, only in proper profile |
| attestation | no |
| execution_allowed | no |
