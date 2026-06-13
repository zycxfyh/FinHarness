# Receipt Usage Audit

Date: 2026-06-13
Status: thin audit surface

## Purpose

`receipt_usage_audit` answers one narrow question:

```text
Which receipts are referenced by reviews, lessons, reports, or other project
knowledge artifacts, and which receipts are currently unreferenced?
```

It helps separate useful evidence from receipt noise. It does not validate
receipt correctness, close lessons, authorize trading, or decide project
quality.

## Entry Point

```bash
task receipt:usage-audit
```

The task writes:

```text
data/receipts/receipt-usage-audit/latest.json
```

That output is ignored because it is a generated observation, not a durable
source artifact.

## Classification

```text
consumed:
  referenced by docs/reviews, docs/lessons, docs/reports, or architecture /
  operations governance docs.

draft_consumed:
  referenced only by docs/lessons/drafts.

referenced:
  referenced by notes, proposals, think docs, ideas, or research assets.

unreferenced:
  no text reference found in the scanned project knowledge surface.
```

## Evidence Surface Layers

The audit also derives a cleanup-oriented `evidence_layer`:

```text
durable_consumed:
  a receipt referenced by reviews, promoted lessons, reports, or architecture /
  operations governance docs. This is the strongest durable evidence layer.

candidate_or_draft:
  a receipt referenced only by lesson drafts, proposals, notes, think docs,
  ideas, or research assets. It may be useful, but it is not promoted evidence.

generated_runtime_or_unlinked:
  a receipt with no text reference in the scanned knowledge surface. Treat as
  generated runtime evidence unless a human promotes it.

missing_reference:
  a text reference points to a receipt that is not present in the checkout.
  This is a documentation/evidence drift signal, not proof the reference is bad.
```

The audit also reports `missing_references`: text references to receipt files
that are not present in the current checkout. After runtime cleanup, these are
expected for old generated receipts unless the project decides to restore or
promote a specific historical receipt.

## Boundary

This audit observes reference usage only. A referenced receipt may still be
wrong, incomplete, stale, or irrelevant. An unreferenced receipt may still be
temporarily useful for local debugging. Human review decides what to promote,
archive, or delete.
