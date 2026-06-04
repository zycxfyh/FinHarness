# License Decision Memo

FinHarness currently has no repository license. This memo compares options for
RC0.1. It does not create a `LICENSE` file and does not grant usage rights.

## Decision Needed

Pick a license posture before a public release candidate is announced. Until
then, external users should treat the repository as all rights reserved except
where GitHub's normal viewing/forking terms apply.

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

## Recommendation

For RC0.1, keep the repository unlicensed until the product/open-source strategy
is explicit. Prepare two candidate paths for user decision:

- If the goal is broad developer adoption: Apache-2.0.
- If the goal is productization with controlled commercial use: source-available
  or proprietary-first, then revisit open-source modules later.

Do not add `LICENSE` until the user confirms the desired legal posture.
