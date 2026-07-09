"""Authority eligibility policy v0.

Agentic-space dimension: Authority Space.

Derives eligibility from evaluation status:

  pass  → eligible
  warn  → deferred
  block → not_eligible

Keeps human confirmation as a gate but does NOT allow it to override
evaluation semantics. This ensures the evaluation chain is not bypassed.
"""

from __future__ import annotations

from typing import Literal


def eligibility_from_evaluation_status(
    status: Literal["pass", "warn", "block"],
) -> Literal["eligible", "deferred", "not_eligible"]:
    """Map evaluation status to authority eligibility.

    Rules:
      pass  → eligible  (system says ok, human confirms)
      warn  → deferred  (system has concerns, human must resolve)
      block → not_eligible (system says no, cannot proceed)

    Human confirmation is still required, but it does not override
    the evaluation result. warn+confirm = deferred, not eligible.
    """
    if status == "pass":
        return "eligible"
    if status == "warn":
        return "deferred"
    return "not_eligible"
