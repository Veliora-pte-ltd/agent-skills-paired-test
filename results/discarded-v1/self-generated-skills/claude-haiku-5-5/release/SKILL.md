---
name: release
description: Cut a tillroll release following the repo's conventions - pick the version bump, run tests, apply pending SQL migrations, bump the version in pyproject.toml and __init__.py, move the Unreleased changelog into a dated version section, write release/X.Y.Z.toml, commit as "Release X.Y.Z", and create the annotated vX.Y.Z tag. Use when the user asks to cut, prepare, tag, or ship a new tillroll version or release.
---

# Cutting a tillroll release

tillroll is a Python package (`src/tillroll`, tests in `tests/`) with SQL migrations in `db/`. Releases are recorded in three places that must agree: the version in code, `CHANGELOG.md`, and `release/<version>.toml`. Follow the steps in order. Stop and ask the user when a step needs a decision that this document does not settle.

## 0. Preconditions

- Run `git status`. The working tree must be clean, and you should be on `main`. If not, stop and ask.
- Read the current version from `pyproject.toml` (`version = "..."`). It should match `__version__` in `src/tillroll/__init__.py` and the latest `release/*.toml`. If they disagree, stop and report it.
- Check that the tag does not exist yet: `git tag --list 'v<new>'` must print nothing.
- Read `## [Unreleased]` in `CHANGELOG.md`. If it has no entries, there is nothing to release; stop and say so.

## 1. Choose the version

- Use `X.Y.Z` (no `v` prefix in files; the tag is `vX.Y.Z`).
- Bump field: the repo records `bump = "patch" | "minor" | "major"` in each release file.
- Precedent is not strict. 1.4.0 (Added + Changed) was a minor bump, but 1.4.2 added a table and was still a patch. Do not infer the bump from changelog headings. Propose one, and confirm it with the user before continuing.
- `prerelease = false` for normal releases. Only set it to `true` if the user explicitly asks for a pre-release.
- Use today's date in ISO format: `date +%F`.

## 2. Run the tests

```bash
python -m pytest
```

If pytest is missing, install the declared test extra (`pip install -e ".[test]"`) and retry. If any test fails, stop and report the output. Do not release on a red suite.

## 3. Apply pending migrations (only if there are new ones)

Migrations live in `db/migrations/NNNN_name.sql` and are listed in order in `db/migrations/manifest.json`. Each file has this header:

```sql
-- migration: 0005
-- ticket: OPS-412
-- reversible: yes
-- +up
...
-- +down
...
```

Compare the highest id in `manifest.json` with `last_migration` in the previous `release/*.toml`. For any migration not yet in a release:

1. Check that the file has the header above, both `-- +up` and `-- +down` sections, and a ticket reference.
2. Make sure its entry in `manifest.json` exists, with `"id"`, `"file"`, and `"sha256"`. Compute the hash with `sha256sum db/migrations/<file>` and fill it in. Never hand-type a hash, and never change the hash of a migration that is already released.
3. Regenerate the schema. Do not edit `db/schema.sql` by hand; it is marked as generated:
   ```bash
   PYTHONPATH=src python3 -m tillroll.db dump-schema
   ```
4. Check `git diff db/schema.sql`. It should show only the expected change for the new migrations.

If there are no new migrations, leave `db/` untouched.

## 4. Bump the version in code

Set the same new version in both places, and nowhere else:

- `pyproject.toml`: `version = "X.Y.Z"` under `[project]`
- `src/tillroll/__init__.py`: `__version__ = "X.Y.Z"`

## 5. Update `CHANGELOG.md`

Keep a Changelog format, as in the existing file.

- Keep an empty `## [Unreleased]` heading at the top of the list.
- Directly below it, add `## [X.Y.Z] - YYYY-MM-DD` and move the existing Unreleased sections under it, unchanged.
- Use the section headings already in use: `### Added`, `### Changed`, `### Fixed`. Keep them in that order and omit empty ones.
- Entries are bullets ending with a period and a ticket reference in parentheses, e.g. `- Optional phone number on customers (OPS-412).`. Do not invent ticket numbers. If an entry has none, ask the user.
- Update the link references at the bottom of the file:
  - `[Unreleased]: https://git.tillroll.example/tillroll/compare/vX.Y.Z...HEAD`
  - Add `[X.Y.Z]: https://git.tillroll.example/tillroll/compare/v<previous>...vX.Y.Z`, placed in version order with the existing links.

## 6. Write the release file

Create `release/X.Y.Z.toml` (the name uses the version without `v`). Mirror the existing files exactly:

```toml
version = "X.Y.Z"
date = "YYYY-MM-DD"
bump = "patch"            # or "minor" / "major", as agreed in step 1
previous = "<previous version>"
prerelease = false
migrations = []           # ids first shipped in this release, e.g. ["0005"]
last_migration = "0004"   # highest migration id in manifest.json after this release
```

- `migrations` lists only the ids that this release introduces. It is `[]` when there are none.
- `last_migration` is the highest id in `manifest.json`, even when this release adds no migrations.

## 7. Commit

Stage only the files you changed for the release: `CHANGELOG.md`, `pyproject.toml`, `src/tillroll/__init__.py`, `release/X.Y.Z.toml`, and, if step 3 applied, `db/migrations/manifest.json`, `db/schema.sql`, and the new migration files. Check with `git status` that nothing else is staged. Feature and fix commits are separate and should not be mixed into the release commit.

Commit message, matching the existing history:

```
Release X.Y.Z
```

## 8. Tag

The repo uses annotated tags named `vX.Y.Z`, with the message `Release X.Y.Z`:

```bash
git tag -a vX.Y.Z -m "Release X.Y.Z"
```

Verify with `git tag -n` and `git show --stat vX.Y.Z`.

## 9. Push (ask first)

Pushing the branch and the tag is outward-facing and cannot be undone once others fetch it. Do not push unless the user explicitly asks. When you ask, show the commit and tag names and the remote. Use `git push origin main` followed by `git push origin vX.Y.Z`.

## Checklist

- [ ] Clean tree on `main`; tag `vX.Y.Z` does not exist
- [ ] Bump type confirmed with the user
- [ ] `python -m pytest` passes
- [ ] New migrations: manifest entries with sha256, `db/schema.sql` regenerated
- [ ] `pyproject.toml` and `__init__.py` show the new version
- [ ] `CHANGELOG.md`: dated section, empty Unreleased, compare links updated
- [ ] `release/X.Y.Z.toml` written with `migrations` and `last_migration` correct
- [ ] Commit `Release X.Y.Z` contains only release files
- [ ] Annotated tag `vX.Y.Z` created
- [ ] Push only after explicit confirmation
