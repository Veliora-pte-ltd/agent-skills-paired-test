---
name: release
description: Cuts a tillroll release or release candidate by choosing the version and updating the version strings, CHANGELOG.md and the release/ metadata file. Use when asked to cut, prepare or ship a release or release candidate. Not for publishing packages or deploying.
---

# Cutting a tillroll release

## Fast path

1. Choose the bump from the sections under `## [Unreleased]`:
   - `### Breaking` or `### Removed` present: **major**
   - otherwise `### Added`, `### Changed` or `### Deprecated` present: **minor**
   - otherwise (only `### Fixed` / `### Security`): **patch**

   A release candidate is the next version plus `rcN` with no separator (PEP 440), e.g. `1.5.0rc1`.
2. Set the version in `pyproject.toml` (`[project] version`) and in `src/tillroll/__init__.py` (`__version__`).
3. `CHANGELOG.md`:
   - Turn the Unreleased block into `## [X.Y.Z] - YYYY-MM-DD` (today's date) and put a new, empty `## [Unreleased]` above it.
   - Section order: Breaking, Added, Changed, Deprecated, Removed, Fixed, Security. Keep every entry word for word.
   - Links at the bottom: point `[Unreleased]` at `.../compare/vX.Y.Z...HEAD` and add `[X.Y.Z]: .../compare/v<previous>...vX.Y.Z` below it.
   - Leave older releases untouched.
4. Create `release/X.Y.Z.toml`:

   ```toml
   version = "X.Y.Z"
   date = "YYYY-MM-DD"
   bump = "minor"          # major | minor | patch (for an rc: the bump of the final release)
   previous = "1.4.2"      # the last non-rc release
   prerelease = false      # true for an rc
   migrations = ["0005"]   # manifest ids after the previous release's last_migration ([] if none)
   last_migration = "0005" # highest migration id in db/migrations/manifest.json now
   ```

5. Do not create git tags or commits: CI tags the release after review. Do not edit older `release/*.toml` files.
