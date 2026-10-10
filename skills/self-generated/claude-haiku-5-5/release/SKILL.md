---
name: release
description: Cut a tillroll release following the repo's conventions - pick the version from the Unreleased changelog, bump pyproject.toml and __init__.py, write release/<version>.toml, move Unreleased entries into a dated CHANGELOG section, verify migrations and schema, run tests, commit "Release <version>", and tag vX.Y.Z. Use when the user asks to cut, prepare, or tag a release, or to bump the version.
---

# Cutting a tillroll release

This repo records releases in four places that must agree: the version in
`pyproject.toml`, `__version__` in `src/tillroll/__init__.py`, the
`CHANGELOG.md` section, and a `release/<version>.toml` file. A release is one
commit titled `Release <version>` plus a `vX.Y.Z` tag. Follow the steps in
order and do not skip the checks.

Work on `main` (it is the release branch). Do not push, tag a remote, or
publish anything until the user confirms.

## 1. Preflight

- `git status` must be clean. If it is not, stop and report what is dirty.
- Run the tests: `python -m pytest`. If they fail, stop and report the output.
- Find the last release: `git tag --list 'v*' --sort=-v:refname | head -1`
  and the newest `release/*.toml`. They should agree. If they do not, stop
  and tell the user.
- List unreleased work: `git log --oneline vX.Y.Z..HEAD` (using the last tag)
  and read the `## [Unreleased]` section of `CHANGELOG.md`. If that section
  has no entries, there is nothing to release. Stop.

## 2. Choose the version

Versions are `MAJOR.MINOR.PATCH` with no `v` prefix in files; the git tag
adds the `v`. Use the changelog subsections to choose the bump:

- **patch**: only `### Fixed` entries (as in 1.4.1 and 1.4.2).
- **minor**: any `### Added` or `### Changed` entry, including releases that
  add migrations (as in 1.4.0).
- **major**: no release so far has used it, and nothing in the repo defines
  when it applies. Use it only if the user asks for it.

Bump from the previous version. Do not reuse or skip numbers. Tell the user
which bump you chose and why.

## 3. Check migrations

Migrations are SQL files in `db/migrations/`, named `NNNN_snake_case.sql`
with four-digit sequential ids. Each file has this header and body:

```sql
-- migration: 0005
-- ticket: OPS-412
-- reversible: yes
-- +up
ALTER TABLE customers ADD COLUMN phone TEXT;
-- +down
ALTER TABLE customers DROP COLUMN phone;
```

For this release:

1. Note every migration id that is not in the previous `release/*.toml`.
   These go in the `migrations` list. If there are none, use `[]`.
2. Make sure every migration file has an entry in `db/migrations/manifest.json`
   with its `id`, `file`, and `sha256`. Compute the hash with
   `sha256sum db/migrations/<file>` and check that it matches the manifest.
3. Never edit a migration file or manifest hash that was already released.
   If a shipped migration is wrong, add a new migration instead.
4. If a migration was added or changed, regenerate the schema. Do not edit
   `db/schema.sql` by hand:
   `PYTHONPATH=src python3 -m tillroll.db dump-schema`
   Check the diff and confirm it contains only the expected change.
5. Set `last_migration` to the highest id in `manifest.json`.

## 4. Bump the version in code

Set the same version in both places:

- `pyproject.toml`: `version = "X.Y.Z"` under `[project]`
- `src/tillroll/__init__.py`: `__version__ = "X.Y.Z"`

Grep for the old version string afterwards to catch any other place it appears.

## 5. Write the release manifest

Create `release/X.Y.Z.toml` with exactly these keys, in this order:

```toml
version = "X.Y.Z"
date = "YYYY-MM-DD"        # today, ISO format
bump = "minor"             # or "patch" / "major", matching step 2
previous = "A.B.C"         # the last released version
prerelease = false
migrations = ["0005"]      # ids added since previous, or []
last_migration = "0005"
```

Existing files in `release/` are never edited after they are committed.

## 6. Update the changelog

In `CHANGELOG.md`:

1. Keep an empty `## [Unreleased]` heading at the top. Its entries move
   down.
2. Add a new heading `## [X.Y.Z] - YYYY-MM-DD` directly below it, using the
   same date as the release file. Move the entries there unchanged. Keep the
   subsections in the order `### Added`, `### Changed`, `### Fixed`, and omit
   any that are empty.
3. Entries follow the existing style: start with a capital letter, put code
   names in backticks, end with a full stop, and put the ticket in
   parentheses, for example `(OPS-409)`. Do not add new entries that are not
   already in Unreleased; if one is missing, ask the user.
4. Update the link references at the bottom of the file:
   - `[Unreleased]: .../compare/vX.Y.Z...HEAD`
   - add `[X.Y.Z]: .../compare/vA.B.C...vX.Y.Z`, placed in version order
     above the previous entry.

Keep the same host URL as the existing links.

## 7. Verify before committing

- `python -m pytest` passes.
- `git diff` shows changes only in: `pyproject.toml`,
  `src/tillroll/__init__.py`, `CHANGELOG.md`, `release/X.Y.Z.toml`, and, if
  there was a migration, `db/migrations/manifest.json`, the new migration
  file, and `db/schema.sql`.
- The version in `pyproject.toml`, `__init__.py`, the changelog heading, and
  the release file are all the same.

## 8. Commit and tag

```bash
git add pyproject.toml src/tillroll/__init__.py CHANGELOG.md release/X.Y.Z.toml
# plus any migration files, manifest.json, and schema.sql that changed
git commit -m "Release X.Y.Z"
git tag vX.Y.Z
```

The release commit has the title `Release X.Y.Z` and no body. Use a
lightweight tag, as `v1.4.2` is. Tag the release commit itself.

## 9. Publish (only with the user's go-ahead)

Show the user the commit and tag, then ask before pushing. The changelog's
compare links point at the remote host, so the tag must be pushed for them
to work. When the user confirms, push the branch and tag together, for
example `git push origin main vX.Y.Z`, after checking the remote name with
`git remote -v`.

## Reporting

End with a short summary: the old and new versions, the bump and why, the
migrations included, the test result, the commit hash, and the tag. If you
stopped at any step, say which step and why.
