# Reference

Reference docs are factual lookup material. They should avoid tutorials and
architecture essays.

Current reference surfaces:

- Commands: [Command Reference](commands.md), or run `task --list` for the live
  task list.
- Interfaces: [Interface Reference](interfaces.md).
- Receipts: [Receipt Reference](receipts.md).
- Config and environment variables: [Config And Environment Reference](config-env.md).
- Wheels: [../wheels.md](../wheels.md).
- Policy rules: [../architecture/policy-contract.md](../architecture/policy-contract.md).
- Evidence and receipts: [../architecture/evidence-inventory.md](../architecture/evidence-inventory.md).
- Module responsibilities: [../modules/README.md](../modules/README.md).

Planned reference docs:

- Keep command reference synchronized with `Taskfile.yml`.
- Add detailed schema tables when a layer's receipt shape stabilizes enough to
  need field-by-field API-style reference.

Reference pages should stay factual: commands, fields, schemas, config names,
file paths, and supported boundaries. Put motivation and trade-offs in
[Explanation](../explanation/README.md), not here.
