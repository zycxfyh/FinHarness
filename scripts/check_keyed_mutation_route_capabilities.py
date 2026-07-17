"""Audit the canonical keyed-mutation registry against runtime routes and dispatch."""

from __future__ import annotations

import json

from finharness.api.app import create_app
from finharness.api.keyed_mutation_capabilities import (
    audit_keyed_mutation_route_capabilities,
    load_keyed_mutation_route_capabilities,
)
from finharness.api.routes_proposals import (
    identity_mutation_reconciliation_dispatcher_ids,
)


def main() -> int:
    audit = audit_keyed_mutation_route_capabilities(
        create_app(),
        load_keyed_mutation_route_capabilities(),
        dispatcher_resolver_ids=identity_mutation_reconciliation_dispatcher_ids(),
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
