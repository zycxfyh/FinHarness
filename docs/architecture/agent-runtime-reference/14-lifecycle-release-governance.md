# 14 Lifecycle / Release Governance

Hermes shows that mature Agent systems need a lifecycle layer: diagnostics, migrations, compatibility, contribution rules, skill/tool/plugin placement, cross-platform care, and state preservation.

For FinHarness, this layer protects long-term capital governance state while the system keeps changing.

## Hermes Pattern

Hermes prioritizes bug fixes, cross-platform compatibility, security hardening, performance, and robustness ahead of new capabilities.

It also uses:

- doctor diagnostics;
- canonical state directories;
- config/env separation;
- skill vs tool vs plugin placement rules;
- registry and toolset wiring tests;
- skill authoring standards;
- cross-platform rules;
- search-before-build discipline;
- ephemeral prompt injection boundaries;
- install/update method awareness.

## FinHarness Mapping

FinHarness long-term state includes:

- StateCore;
- receipt store;
- proposal queue;
- review events;
- IPS/policy;
- evidence artifacts;
- lessons;
- simulation reports;
- provider configs.

These need schema versions, backup/export policy, migration policy, integrity checks, and PII/secret exclusions.

## Doctor

A future `finharness doctor` should check:

- Python/dependency version;
- StateCore readable;
- receipt root writable;
- IPS present and parseable;
- active profile;
- Agent tool registry;
- profile tool exposure;
- evidence provider availability;
- proposal queue health;
- pending migrations;
- schema versions;
- no broker write tool registered;
- `execution_allowed=false`.

## Capability Placement

| Capability | Placement |
| --- | --- |
| Receipt writer | core |
| Human attestation boundary | core |
| IPS policy engine | core |
| Agent proposal draft tool | core |
| Market data provider | provider registry |
| SEC filing fetcher | provider/plugin |
| PDF table parser | plugin/helper |
| TradingView integration | plugin/provider |
| Broker write | unsupported |
| Tax export renderer | optional plugin/tool |

Evidence extension can be pluginized. Authority boundaries must remain core.

## Migration Policy

Core objects should eventually carry schema versions:

- proposal;
- receipt;
- IPS;
- review event;
- evidence ref;
- context pack.

Migration rules:

- forward migration only by default;
- backup before migration;
- dry-run migration;
- migration receipt;
- rollback note;
- integrity check after migration;
- legacy fixture tests.

## Runtime Docs Are Runtime Surface

Agent-readable docs and skills can shape behavior. They should:

- avoid marketing language;
- avoid implying authority;
- state non-claims;
- require source refs where needed;
- state human review boundaries;
- include verification steps;
- be covered by examples or tests when they govern workflow.

Ephemeral prompt injection should not become persistent authority state.
