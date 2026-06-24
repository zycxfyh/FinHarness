"""Shared valid decision scaffold for tests that create governed proposals.

After P4, ``create_governed_proposal`` (and the POST /proposals route) fail-closed
unless the four required scaffold fields are present. Tests that exercise other
behavior reuse this minimal valid scaffold so the forcing gate is satisfied without
each test re-stating it.
"""

VALID_SCAFFOLD = {
    "decision_intent": "Review the test candidate",
    "thesis": "Surfaced for test coverage",
    "do_nothing_case": "Leave it unchanged; the surfaced condition persists.",
    "risk_if_wrong": "Acting may incur transaction or tax cost.",
}
