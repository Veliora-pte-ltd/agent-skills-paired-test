---
name: release
description: Cut a new tillroll release - choose the semver bump, update the version in pyproject.toml and __init__.py, roll the CHANGELOG, write the release/X.Y.Z.toml record, verify migrations/schema, commit and tag. Use when asked to release, bump the version, or prepare/ship a new version.
---

# Cutting a tillroll release

Conventions below are derived from the repo history (`Release 1.4.0`–`1.4.2`, `CHANGELOG.md`, `release/*.toml`). Do not push or publish anything without the user's confirmation; stop after the local commit and tag and report.

## 1. Preflight

- Working tree must be clean and on `main` (`git status`). Last tag: `git describe --tags --abbrev=0` (tags look like `v1.4.2`, annotated, message `Release 1.4.2`).
- Run `python -m pytest`; do not release on failures.
- Read `## [Unreleased]` in `CHANGELOG.md` and `git log <last-tag>..HEAD`. If Unreleased is empty or doesn't cover the commits, stop and ask rather than invent entries. Each entry ends with its ticket, e.g. `(OPS-412)`.

## 2. Pick the version

Semver, driven by the Unreleased content and migrations since the last release:
- **patch**: only `### Fixed` entries, no new migrations (1.4.1, 1.4.2).
- **minor**: `### Added`/`### Changed` entries or new migrations (1.4.0 added migrations 0002–0004).
- **major**: breaking changes (ask the user to confirm).

If the user supplied a version or prerelease, use it; check it agrees with the changes and flag a mismatch. Otherwise propose the version and confirm.

## 3. Verify migrations and schema

- Every file in `db/migrations/` must be listed in `db/migrations/manifest.json` with a correct `sha256` (`sha256sum db/migrations/*.sql`). Never edit an already-released migration; add a new one instead.
- Each migration needs `-- +up` and `-- +down` sections.
- Regenerate the schema and make sure it produces no diff: `PYTHONPATH=src python3 -m tillroll.db dump-schema` (`db/schema.sql` is generated; never hand-edit).
- Work out `migrations` for this release: ids of migrations added since the previous release's `last_migration` (e.g. `["0005"]`, or `[]` if none). `last_migration` is the highest id in the manifest.

## 4. Edit files (version must match everywhere)

1. `pyproject.toml`: `version = "X.Y.Z"`.
2. `src/tillroll/__init__.py`: `__version__ = "X.Y.Z"`.
3. `CHANGELOG.md`:
   - Keep an empty `## [Unreleased]` heading at the top, then add `## [X.Y.Z] - YYYY-MM-DD` (today's date) containing the former Unreleased sections (order: Added, Changed, Fixed).
   - Update the link references at the bottom: `[Unreleased]: https://git.tillroll.example/tillroll/compare/vX.Y.Z...HEAD` and add `[X.Y.Z]: https://git.tillroll.example/tillroll/compare/vPREV...vX.Y.Z` above the previous version's link.
4. New file `release/X.Y.Z.toml`, same shape as existing ones:
   ```toml
   version = "X.Y.Z"
   date = "YYYY-MM-DD"
   bump = "patch"          # patch | minor | major
   previous = "PREV"       # previous released version
   prerelease = false
   migrations = []         # ids added in this release, e.g. ["0005"]
   last_migration = "0005" # highest id in manifest.json
   ```

## 5. Commit and tag

- Re-run `python -m pytest`; check `git diff` touches only the files above.
- Commit all of them in one commit with the message `Release X.Y.Z` (plus any required trailer).
- Create the annotated tag: `git tag -a vX.Y.Z -m "Release X.Y.Z"`.
- Report the version, bump reasoning, and the commands for pushing (`git push origin main vX.Y.Z`); only run them if the user says so.
