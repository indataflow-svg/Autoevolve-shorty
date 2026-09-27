# Upgrading and backups

Company Core stores operational state under `data/` and generated project
artifacts under `projects/`. Both are intentionally outside Git.

## Back up

Use the backup script. It snapshots every SQLite database with the SQLite
online backup API, so it is safe while the application is running, and it
records checksums, schema hashes and row counts in a manifest:

```bash
make backup
# or: ./scripts/backup.sh --out /path/to/backups
```

The archive lands in `backups/company-core-<timestamp>.tar.gz` with a `.sha256`
sidecar. Never copy a live database with `cp`: WAL frames live in `-wal`/`-shm`
side files and a plain copy of the main file can be torn.

Protect the backup because it can contain credentials, contacts, emails and
campaign media. Set `BACKUP_AGE_RECIPIENT` (age) or `BACKUP_GPG_RECIPIENT`
(gpg) to encrypt every archive on creation. Retain multiple tested restore
points.

Example cron entry (daily at 03:15):

```cron
15 3 * * * cd /srv/company-core && ./scripts/backup.sh --out /srv/backups >> /var/log/company-core-backup.log 2>&1
```

## Verify a backup

```bash
make verify-backup ARCHIVE=backups/company-core-<timestamp>.tar.gz
```

Verification extracts the archive to a temporary directory, recomputes every
checksum, re-reads the schema and compares row counts against the manifest.
Run it after each backup rotation; an archive that does not verify is not a
backup.

## Upgrade

```bash
git fetch --tags
git pull --ff-only
make setup
npm --prefix autoevolve-ui ci
npm --prefix autoevolve-ui run build
make check
```

Read `CHANGELOG.md` before restarting. `make setup` preserves the existing
`.env` and local config. Compare `.env.example` with `.env` manually to
discover newly added settings.

## Restore or roll back

1. Stop the application.
2. Check out the previous known-good tag or commit and reinstall its
   dependencies (`make setup`).
3. Check the archive first:

```bash
./scripts/restore.sh --verify --archive backups/company-core-<timestamp>.tar.gz
```

4. Restore it. The apply mode refuses to run while the target still looks like
   a live instance (`uvicorn app.api` running); use `--force` only after the
   services are actually stopped:

```bash
./scripts/restore.sh --apply --archive backups/company-core-<timestamp>.tar.gz
```

Do not run an older release against data that has undergone an incompatible
migration unless the release notes explicitly allow it.

After any restore, run `make doctor`, start the service, verify `/health`, and
inspect one saved lead and campaign before resuming outbound actions.
