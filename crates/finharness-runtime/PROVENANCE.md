# Runtime provenance

The execution kernel was transplanted from Ordivon commit
`f0660a5b8bb75208fed4660f1d21152d0c09dfb8` under Apache-2.0.

FinHarness owns this copy and evolves it independently. The inherited kernel
preserves Job/Attempt identity, idempotent admission, capacity reservations,
systemd/cgroup process ownership, bounded Artifacts, cancellation, terminal
commit, and restart/orphan recovery. Git workspace and MCP surfaces are not a
FinHarness product interface.
