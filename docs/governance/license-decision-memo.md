# License Decision Memo

FinHarness uses the Apache License 2.0 for RC0.1 and later repository work
unless superseded by a future explicit legal decision.

## Decision

Apache-2.0 was selected because FinHarness is infrastructure-style engineering
software where broad adoption, clear patent terms, and standard open-source
compatibility matter more than reciprocal source-control restrictions.

## Options

| Option | Commercialization | Closed-source reuse by others | Fit for current stage | Main risk |
| --- | --- | --- | --- | --- |
| Proprietary / no OSS license | Strong owner control | Not permitted without permission | Good if product direction is private | Low community adoption and Scorecard License remains 0 |
| MIT | Allowed | Allowed | Simple and common for early OSS | Gives broad reuse rights with limited patent language |
| Apache-2.0 | Allowed | Allowed | Strong default for infrastructure-style OSS | More formal; still allows competitors to reuse |
| GPL-3.0 | Allowed under copyleft | Not for closed-source redistribution | Good if reciprocal openness matters | Can reduce commercial adoption |
| AGPL-3.0 | Allowed under network copyleft | Strongly restricts SaaS-style closed reuse | Good if hosted derivatives must open source | Often avoided by commercial users |
| PolyForm / BSL-style | Usually controlled by terms | Usually restricted | Good for open-core or delayed-open models | Less standard; needs careful legal review |

## Evaluation

FinHarness is a governance and research harness, not merely a utility library.
The project includes trading boundaries, receipts, and methodology that may
become product differentiation. A permissive license could accelerate adoption
but also allows closed-source reuse of the governance method. A reciprocal or
source-available license protects more of the method but may reduce ecosystem
contribution and integration.

## Superseded Recommendation

The earlier RC0.1 recommendation was to keep the repository unlicensed until
the product/open-source strategy was explicit. That recommendation is now
superseded by the Apache-2.0 decision.

If future productization needs a different posture, handle it as a new legal
and governance decision rather than as an incidental engineering change.

## Implementation

- Repository license file: `LICENSE`
- Package metadata: `pyproject.toml` declares `Apache-2.0`
- Scorecard License finding is expected to close after GitHub reindexes the
  default branch and the scorecard workflow uploads fresh SARIF.
