"""Legacy surface deprecation headers helper.

Adds X-FinHarness-Legacy-Surface and X-FinHarness-Superseded-By headers
to responses from legacy routes, telling callers these are old surfaces
that should migrate to Execution Kernel endpoints.
"""

from fastapi import Response

ACTION_INTENT_SUPERSEDED_BY = (
    "/execution/order-drafts, /execution/orders, /execution/reports"
)

PAPER_VALIDATION_SUPERSEDED_BY = (
    "/execution/order-drafts, /execution/orders/{id}/submit, /execution/reports"
)


def mark_legacy_surface(response: Response, superseded_by: str) -> None:
    """Set legacy deprecation headers on the response."""
    response.headers["X-FinHarness-Legacy-Surface"] = "true"
    response.headers["X-FinHarness-Superseded-By"] = superseded_by
