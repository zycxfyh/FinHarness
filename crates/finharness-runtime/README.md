# FinHarness Runtime

This crate is the private recoverable execution kernel embedded in FinHarness.

The product-facing boundary accepts only registered capital operations with a Principal,
Agent runtime, domain reference, exact context digest, and resource concurrency key. It does
not expose arbitrary executable, environment, Git workspace, file mutation, or MCP tools.

The inherited transactional kernel owns Job/Attempt identity, idempotent admission, capacity
reservation, systemd/cgroup process ownership, cancellation intent, bounded Artifacts, terminal
commit, and restart/orphan recovery. Capital World, Mission, Delegation, Risk, broker truth,
reconciliation, and Consequence remain owned by the Python FinHarness domain.

See `PROVENANCE.md` for the source transplant.
