# State API query budget

State collection routes are read models over accumulating history, so an omitted
query parameter must never mean "load the whole table".

The collection routes under `/state/*` and `/snapshots` return their existing bare
JSON arrays for compatibility. Every route applies a stable SQL order followed by
`offset` and `limit`. The default limit is 100 rows and the maximum is 200 rows;
`offset` defaults to zero. Primary identifiers are the final ordering key so pages
are deterministic while the underlying rows remain unchanged.

`/state/positions` additionally requires `snapshot_id`. This makes the historical
scope explicit and prevents a caller from accidentally combining positions from
every portfolio snapshot. A missing scope is a validation error, not an implicit
request for current or historical truth. The referenced Snapshot must exist in
State Core: an unknown identifier returns a typed `snapshot_not_found` response,
while an existing Snapshot with zero positions returns the existing empty array.
Snapshot existence is independent of Snapshot kind; this route does not resolve
which Snapshot is current or admit it as capital truth.

`/dashboard/summary` is not a collection escape hatch. Counts and monetary totals
are SQL aggregates, while latest snapshot and receipt lookups are bounded current
projections. The dashboard does not materialize complete state tables to compute a
summary.
