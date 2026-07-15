# Audit The Issue Backlog Taxonomy

GitHub Issue state and labels are canonical. The repository does not mirror live
Issue status into a database or committed Markdown table.

Run the read-only cardinality audit from a repository checkout:

```bash
task issues:audit
```

To target an explicit repository:

```bash
task issues:audit -- --repo zycxfyh/FinHarness
```

Every open Issue must have exactly one label from each dimension:

- `plane:*`: primary architecture owner;
- `type:*`: work kind;
- `status:*`: lifecycle and authorization posture.

Issue Forms only record the requested plane and lifecycle because a dropdown
cannot dynamically apply labels. The reviewer applies the matching labels after
creation and reruns the audit. `status:dormant` and `status:deferred` do not
authorize implementation; `status:temporary` requires an exit condition.

Use GitHub-native searches for current views:

- [active work](https://github.com/zycxfyh/FinHarness/issues?q=is%3Aissue%20is%3Aopen%20label%3A%22status%3Aactive%22)
- [dormant work](https://github.com/zycxfyh/FinHarness/issues?q=is%3Aissue%20is%3Aopen%20label%3A%22status%3Adormant%22)
- [deferred gates](https://github.com/zycxfyh/FinHarness/issues?q=is%3Aissue%20is%3Aopen%20label%3A%22status%3Adeferred%22)
- [temporary owners](https://github.com/zycxfyh/FinHarness/issues?q=is%3Aissue%20is%3Aopen%20label%3A%22status%3Atemporary%22)
- [product plane](https://github.com/zycxfyh/FinHarness/issues?q=is%3Aissue%20is%3Aopen%20label%3A%22plane%3Aproduct%22)
- [assurance plane](https://github.com/zycxfyh/FinHarness/issues?q=is%3Aissue%20is%3Aopen%20label%3A%22plane%3Aassurance%22)

These queries are views, not completion evidence. Dependency order and opening
conditions remain in the canonical Program and native Issue relationships.
