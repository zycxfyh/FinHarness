# Control Owner — Execution Spec (NOW-3 / G05)

Executable spec for the meta-governance gap: the per-action human attestation
exists, but **no named human owns the control system as a whole.** Today the only
things validating FinHarness are two AIs and a user who cannot read the code.
NOW-3 adds the institutional answer — a named human who **periodically certifies
the brakes are in force and unweakened**, with a dated receipt a third party can
check. It is the analog of the SEC 15c3-5 requirement that a named officer
certify the market-access controls. See gap **G05** in
[07 Final Merged Plan](industry-benchmark/07-final-merged-plan.md) and
[discipline-layer-baseline.md](discipline-layer-baseline.md).

**No new dependency** (pydantic + stdlib subprocess/unittest). This is a **human
action**; AI may draft but cannot self-certify (mirrors lesson→rule: AI drafts,
a human promotes).

## 0. Pattern to mirror (verified)

`rule_change_ledger.py` already encodes the right shape: a frozen pydantic record,
a **non-empty `attester`** required (fail-closed, never a default), and a
state+receipt JSON written via `_write_json`. NOW-3 reuses this exactly, with the
control owner in the attester role.

The certification's **evidence** is the discipline-layer baseline test set
(`discipline-layer-baseline.md` §3): `tests/test_execution.py`,
`tests/test_risk_gate*.py`, `tests/test_hardening_gate.py`,
`tests/test_post_trade.py` — the guards for the 8 must-hold invariants.

## 1. New module `src/finharness/control_owner.py`

```python
class ControlCertification(BaseModel):
    model_config = ConfigDict(frozen=True)
    schema_version: str = "finharness.control_certification.v1"
    certification_id: str
    created_at_utc: str
    control_owner: str            # the named human; never empty
    review_cadence_days: int
    next_review_due_utc: str
    controls_in_force: list[str]  # invariant ids from the baseline (e.g. "INV-1".."INV-8")
    baseline_passed: bool
    baseline_evidence: dict[str, Any]   # test modules, pass/fail counts, returncode
    status: Literal["certified", "not_certified"]
    non_certification_statement: str
```

- `ControlCertificationError(RuntimeError)` for refusals.
- `CONTROL_BASELINE_INVARIANTS` = the 8 invariant ids/titles from
  `discipline-layer-baseline.md` §2.
- `NON_CERTIFICATION_STATEMENT` = a fixed disclaimer (see §3).

`certify_controls(...)` — a **pure, testable** function:

```python
def certify_controls(*, control_owner, review_cadence_days,
                     baseline_passed, baseline_evidence,
                     controls_in_force=CONTROL_BASELINE_INVARIANTS,
                     state_root=None, receipt_root=None) -> ControlCertification:
```

- **Fail-closed:** `control_owner.strip()` empty → raise `ControlCertificationError`
  ("certification requires a named human control owner").
- **Cannot certify failing brakes:** `status = "certified" if baseline_passed
  else "not_certified"`. A `not_certified` record is still written (it is the
  honest evidence that the brakes did **not** pass on that date).
- `next_review_due_utc` = `created_at + review_cadence_days`.
- Writes `state/control-certifications/<id>.json` and
  `receipts/control-certifications/receipt_<id>.json` (mirror `_write_json`).
- `load_certifications`, `latest_certification`, and `audit_overdue(now)` →
  ids whose `next_review_due_utc` is in the past (escalate to a human).

## 2. Script + task (the human action)

`scripts/run_control_certification.py` + `task governance:certify-controls`:

```bash
task governance:certify-controls -- --owner "<name>" --cadence-days 30
```

- **Fail-closed:** missing/empty `--owner` → non-zero exit, no receipt.
- Runs the baseline guard tests via subprocess unittest; captures returncode +
  pass/fail counts into `baseline_evidence`.
- Calls `certify_controls(...)`; writes the certification receipt; prints it with
  `execution_allowed=false`.
- Exit non-zero if `status == "not_certified"` (a failed-brakes certification is a
  governance failure to surface, not a pass).

## 3. Red lines

- **Named human required, never a default** — empty owner is refused (fail-closed,
  like `attester`).
- **A human, not the AI, certifies.** The task is run by a person who types their
  name; AI may prepare/draft but the attestation is the human's.
- **Cannot certify brakes that fail their tests** — `baseline_passed=false` →
  `not_certified`.
- **Not legal/compliance certification.** `NON_CERTIFICATION_STATEMENT`:
  *"This is a local control-owner attestation that the project's safety
  invariants were tested on this date. It is not SEC/FINRA/legal compliance
  certification, not a release approval, and not live-trading authorization."*
- **No execution authority.** The model has no `execution_allowed`/authority
  field; this is governance evidence, never a trade gate.
- **No new dependency.**

## 4. Tests (`tests/test_control_owner.py`)

1. Empty owner → `ControlCertificationError` (fail-closed).
2. `baseline_passed=True` → `status="certified"`, receipt written with owner,
   `created_at_utc`, `next_review_due_utc`, `baseline_evidence`, and the
   non-certification statement.
3. `baseline_passed=False` → `status="not_certified"` (still recorded).
4. `next_review_due_utc` = created + cadence; `audit_overdue` flags a past-due
   certification.
5. Model carries **no** `execution_allowed`/authority field.
6. `NON_CERTIFICATION_STATEMENT` explicitly disclaims legal/compliance/release/
   live authority.

## 5. Acceptance checklist

- [ ] `control_owner.py` added (frozen model, `certify_controls`, load/latest/
      audit_overdue), mirroring `rule_change_ledger` state+receipt writing.
- [ ] Empty owner refused; AI cannot self-certify (human runs the task).
- [ ] `baseline_passed=false` → `not_certified`; the certification records it.
- [ ] `scripts/run_control_certification.py` + `task governance:certify-controls`
      run the baseline guard tests and write a dated receipt; non-zero on
      `not_certified` or missing owner.
- [ ] No execution authority field; non-certification statement present.
- [ ] New tests (§4) green; existing suite green; `ruff` clean; `task check`
      passes. (`security:scan` not needed.)
- [ ] Report with test evidence, not a bare "done".

## 6. Out of scope

- Periodic scheduling/reminders (a later operations concern).
- Cryptographic signing of the certification (gap G14 records-integrity, later).
- Any change to the controls themselves — this phase certifies them, it does not
  modify `risk_gate`/`trading_guard`/`execution`.
