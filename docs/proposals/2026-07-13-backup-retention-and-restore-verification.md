# Backup Retention And Restore Verification Mini-RFC

- Status: implemented
- Classification: C3
- Issue: #351
- Parent: #343

## Decision

State Core backups are published only after a capacity preflight, creation in a
same-filesystem staging directory, SHA-256 binding of both the SQLite snapshot
and receipt archive, and an immediate restore-readiness verification. The final
directory rename is the publication boundary; `.incomplete-*` directories are
never treated as valid backups.

The backup root is configurable and may be an off-device mounted filesystem.
Capacity is measured at that destination. The conservative preflight requires
free space for the uncompressed source DB and receipt files plus a configurable
reserve; failure occurs before any backup artifact is created.

## Restore-readiness contract

`task backup:verify -- BACKUP` checks the v2 manifest, relative-path confinement,
artifact sizes and hashes, SQLite `PRAGMA quick_check`, and full readable traversal
of a receipt archive containing only regular files/directories below `receipts/`.
It never writes to or replaces production state. A missing, corrupt, path-escaping,
or structurally unsafe artifact fails closed.

## Retention contract

`task backup:prune` is dry-run by default. `--apply` is required for deletion.
Only fully verified backup directories are eligible. The newest configured count
is protected, the newest valid backup is always protected, `.legal-hold` excludes
a backup, and unknown, incomplete, invalid, or symlinked directories are skipped.
Verified backups beyond the protected count become eligible only after the age
threshold.

Defaults are a 512 MiB free-space reserve, seven protected backups, and a 30-day
age threshold. Operators can override these with `FINHARNESS_BACKUP_*` settings or
command flags. Retention is deliberately not run automatically during backup, so
a capacity failure cannot silently broaden authority into deletion.

## Failure and rollback

Creation failures remove only their uniquely named staging directory. Published
backups are immutable inputs to verification. The operational rollback is to stop
using the new prune command and retain existing backup directories; the v1 reader
is not silently accepted as v2 restore evidence. No command grants execution or
release authority.
