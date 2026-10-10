---
name: release
description: Cut a new tillroll release - choose the version, update the version strings, CHANGELOG.md, release/<version>.toml record and migration state, then commit and tag. Use when asked to release, publish, tag, or bump the version of this project.
---

# Cutting a tillroll release

Everything below is derived from the repo's history (the `Release 1.4.2` commit and `release/*.toml`). Do the steps in order. Do not push, or create remote releases, unless the user asks.

## 1. Preflight

- `git status` must be clean and you should be on `main`. If not, stop and ask.
- Run `python -m pytest`; it must pass.
- Read `CHANGELOG.md`. The `## [Unreleased]` section must contain entries; if empty there is nothing to release.
- Find the last release: highest `release/<version>.toml` (and matching `vX.Y.Z` git tag). Call it `PREV`.
- Verify migration integrity: for every entry in `db/migrations/manifest.json`, `sha256sum db/migrations/<file>` must equal its `sha256`. Every migration file added since `PREV` must be in the manifest (a new one needs `id`, `file`, `sha256`). A released migration that has been edited is a problem: stop and report it.
- Verify `db/schema.sql` is current: run `PYTHONPATH=src python3 -m tillroll.db dump-schema` and confirm `git diff db/schema.sql` is empty (the file is generated, never hand-edit it). If the diff is non-empty, report it and, if appropriate, include the regenerated file in the release commit.

## 2. Choose the version

Semantic versioning, `MAJOR.MINOR.PATCH`, current version in `pyproject.toml`.
- Precedent: only `### Fixed` entries -> `patch` (1.4.1); `Added` together with `Changed` -> `minor` (1.4.0). Note 1.4.2 shipped an `Added`-only change (new table) as a `patch`, so the precedent is not fully consistent. If the Unreleased section contains `Added` or `Changed` entries, state your choice of bump and reasoning, and confirm with the user if they have not specified a version.
- Breaking changes -> `major`.

## 3. Edit files (the release commit touches exactly these)

1. **`pyproject.toml`**: `version = "X.Y.Z"`.
2. **`src/tillroll/__init__.py`**: `__version__ = "X.Y.Z"` (must match pyproject).
3. **`CHANGELOG.md`** (Keep a Changelog style):
   - Leave an empty `## [Unreleased]` heading, and put the previous Unreleased entries under a new `## [X.Y.Z] - YYYY-MM-DD` heading directly below it (use today's date; entries keep their `### Added/Changed/Fixed` subsections and ticket IDs like `(OPS-123)`).
   - Update the link references at the bottom: `[Unreleased]: https://git.tillroll.example/tillroll/compare/vX.Y.Z...HEAD`, and add `[X.Y.Z]: https://git.tillroll.example/tillroll/compare/vPREV...vX.Y.Z` above the previous version's link.
4. **`release/X.Y.Z.toml`**: new file in the same shape as the existing ones:
   ```toml
   version = "X.Y.Z"
   date = "YYYY-MM-DD"
   bump = "patch"            # patch | minor | major, relative to previous
   previous = "PREV"
   prerelease = false
   migrations = ["0005"]     # ids of migrations added since PREV, [] if none
   last_migration = "0005"   # highest id in db/migrations/manifest.json
   ```
   `migrations` = manifest ids not present in the previous release's `last_migration` range; `last_migration` carries forward from the previous file if there are none (see 1.4.1).

## 4. Verify, commit, tag

- Re-run `python -m pytest`; check `git diff` shows only the files above.
- Commit with message `Release X.Y.Z` (the subject used for prior releases), ending with the required co-author trailer.
- Create the tag `vX.Y.Z` on that commit (existing tags are lightweight: `git tag vX.Y.Z`).
- Report the result and note that nothing has been pushed. Push the commit and tag only if the user asks.
