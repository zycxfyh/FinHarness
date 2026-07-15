# Manage Issue Worktrees

FinHarness keeps the main delivery rule deliberately small: one leaf issue,
one numbered branch/worktree, one PR, and no next implementation until the
current PR passes CI and merges.

## Start

Run this from any active FinHarness worktree:

```bash
task issue:start -- 336 --slug worktree-lifecycle
```

The command verifies that the issue is open, fetches current `origin/main`, and
creates the deterministic pair:

```text
branch:   agent/336-worktree-lifecycle
worktree: <main-worktree-parent>/finharness-336
```

It refuses existing paths, existing checked-out branches, malformed slugs, and
closed issues.

## Inspect

```bash
task issue:status -- 336
task issue:status
```

Status is read-only. It reports branch/path/issue-number mismatches, prunable
metadata, and dirty worktrees.

## Hand Off A Validated PR To CI

Keep the PR in draft while implementation is incomplete. After the branch has
passed `task check:ci`, render a complete body. The command derives the issue
number from the branch and the changed-file list from the committed diff:

```bash
task pr:body -- \
  --scope "Concise description of the reviewed change" \
  --risk low --classification C1 \
  --validation "task check:ci — passed" \
  --negative-evidence "Named failing fixture or N/A — reason" \
  --persistence "Restart evidence or N/A — reason" \
  --rollback "Concrete rollback action"
```

Use that output for both UI-created and programmatically created PRs. Then push
the exact validated head, mark the PR ready, and arm squash auto-merge:

```bash
gh pr ready <pr-number>
gh pr merge <pr-number> --auto --squash --delete-branch=false
```

Do not use `--admin` to bypass the ruleset. Auto-merge waits for the active
required checks and branch rules; a failed required check blocks the merge.
The browser golden-path job remains an explicitly optional signal, so review
its result separately when the change touches the cockpit.

PR workflow runs share a per-PR concurrency group. Pushing a newer commit
cancels the superseded run for that workflow. Commit evidence distinguishes:

```text
PR head:     the submitted topic commit
merge ref:   GitHub's synthetic integration commit for the PR and base
main commit: the final squash/rebase/merge commit delivered to main
```

`Local verification` explicitly checks out the PR head on pull requests and the
final main commit on main pushes. A separate identity workflow records the PR
head, merge ref, and final main identities as machine-readable artifacts. Do
not call a synthetic merge-ref run "exact head"; name the identity and full SHA.

Pushes to `main`, schedules, and manual dispatches use unique groups instead:
post-merge `main` runs remain intentional evidence for the canonical branch and
are not cancelled as stale PR work.

When an issue's acceptance contract requires evidence from the delivered main
commit, link the PR with `Refs #N`, not `Closes #N`. After merge, keep the issue
open until both the final-main identity job and main-push Local verification
succeed on the same delivered SHA. Then close the issue manually and run the
finish command below.

## Finish After Merge

First preview the exact cleanup plan:

```bash
task issue:finish -- 336
```

Then apply it from the main worktree:

```bash
task issue:finish -- 336 --apply
```

Cleanup is allowed only when the issue is closed, exactly one merged PR exists
for the branch, the local head is the exact PR head, naming is consistent, and
the worktree is clean. Exact PR-head matching is required here because squash
merges do not make the topic commit an ancestor of `main`; ordinary
`git branch -d` cannot prove that cleanup is safe.

The command never deletes arbitrary branches, never discards a dirty worktree,
and does not delete a remote branch. Repository merge settings own remote branch
deletion.
