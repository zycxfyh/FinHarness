# Reference

Reference docs are factual lookup material. They should avoid tutorials and
architecture essays.

Current reference surfaces:

- Commands: [Command Reference](commands.md), or run `task --list` for the live
  task list.
- Interfaces: [Interface Reference](interfaces.md).
- Receipts: [Receipt Reference](receipts.md).
- Financial terminology map: [Financial Terminology Map](financial-terminology-map.md).
- Config and environment variables: [Config And Environment Reference](config-env.md).
- Engineering collaboration roles: [Engineering Roles Cheat Sheet](engineering-roles.md).
- Wheels: [../wheels.md](../wheels.md).
- Framework index: [../architecture/framework-index.md](../architecture/framework-index.md).
- System catalog: [../architecture/system-catalog.yml](../architecture/system-catalog.yml).
- Engineering leverage map: [../architecture/engineering-leverage-map.md](../architecture/engineering-leverage-map.md).
- Governance policy registry: run `task governance:policies`.
- Current-doc fact guard: [../architecture/documentation-fact-governance.md](../architecture/documentation-fact-governance.md).
- Module responsibilities: [../architecture/module-map.md](../architecture/module-map.md).

Planned reference docs:

- Keep command reference synchronized with `Taskfile.yml`.
- Keep receipt schema tables synchronized when receipt fields or direct JSON
  families change.
- Run `task docs:current-check` after editing current navigation or reference
  docs.

Reference pages should stay factual: commands, fields, schemas, config names,
file paths, and supported boundaries. Put motivation and trade-offs in
[Explanation](../explanation/README.md), not here.
