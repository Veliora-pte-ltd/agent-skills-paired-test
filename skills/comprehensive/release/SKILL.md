---
name: release
description: Cuts a tillroll release or release candidate by choosing the version and updating the version strings, CHANGELOG.md and the release/ metadata file. Use when asked to cut, prepare or ship a release or release candidate. Not for publishing packages or deploying.
---

# tillroll releases: the complete guide

This guide explains how tillroll is released: how versions are chosen, what changes in the repository when a
release is cut, how release candidates work, what happens after the release is cut, and how to deal with the
problems that come up. It is written for anyone on the team who cuts a release, which in practice means
whoever is on the release rota that week. A checklist at the end lists every rule in one place.

## 1. Background

tillroll used to be released by tagging whatever was on `main` and writing release notes from memory. That
worked while one person did every release, but as the team grew, version numbers stopped meaning anything
and the operations team could not tell which database migrations a release contained. Since version 1.2 every
release is "cut" in a pull request that changes four things: the version strings, the changelog, and a small
release metadata file. CI tags the release once that pull request has been reviewed and merged.

Cutting a release is therefore a repository change like any other. It does not publish anything, deploy
anything or notify anyone; those steps happen later and are owned by operations.

### 1.1 What the operations team uses

Operations read `release/<version>.toml` to decide how to deploy a release. The `migrations` list tells them
which schema changes are included, which decides whether a maintenance window is needed. The `bump` field
tells them how much risk to expect: a major release triggers a longer staging soak. Getting these fields
right matters more than the prose in the changelog.

## 2. Choosing the version

tillroll uses semantic versioning (`MAJOR.MINOR.PATCH`) with a team rule for deciding the bump, based only on
the section headings under `## [Unreleased]` in `CHANGELOG.md`. Do not second-guess the rule from the content
of the entries; if the sections are wrong, fix the changelog in a separate change first.

- If there is a `### Breaking` or a `### Removed` section: **major** (e.g. 1.4.2 to 2.0.0).
- Otherwise, if there is an `### Added`, `### Changed` or `### Deprecated` section: **minor** (e.g. 1.4.2 to 1.5.0).
- Otherwise, when only `### Fixed` and/or `### Security` are present: **patch** (e.g. 1.4.2 to 1.4.3).

Note that `### Changed` means a minor bump in tillroll, even when the change looks small. This was agreed after
a "small" behaviour change shipped as a patch and broke a downstream report; operations now treat any
behaviour change as at least minor.

### 2.1 Release candidates

When a release needs a trial in staging before it is final, we cut a release candidate. A release candidate
uses the version the final release will have, plus `rcN` with no separator, following PEP 440: `1.5.0rc1`,
then `1.5.0rc2` if a second candidate is needed. Do not write `1.5.0-rc1` or `1.5.0-rc.1`; Python packaging
normalises those differently and our tooling compares strings.

A release candidate is cut exactly like a final release (sections 3 to 5), using the rc version everywhere:
the version strings, the changelog heading, the links and the release file name. In the release file,
`prerelease` is `true` and `bump` is the bump of the final release the candidate leads to.

## 3. Version strings

The version appears in two places, and both must be updated:

- `pyproject.toml`, in the `[project]` table: `version = "X.Y.Z"`;
- `src/tillroll/__init__.py`: `__version__ = "X.Y.Z"`.

There is no other copy of the version in the repository. Do not add one.

## 4. The changelog

`CHANGELOG.md` follows a format close to Keep a Changelog, with a few team rules. When cutting a release:

1. Turn the `## [Unreleased]` block into the new release: its heading becomes `## [X.Y.Z] - YYYY-MM-DD`,
   using today's date in ISO format.
2. Put a new, empty `## [Unreleased]` heading above it, with nothing under it.
3. Put the sections in the release in this fixed order: Breaking, Added, Changed, Deprecated, Removed, Fixed,
   Security. Contributors add sections in whatever order they like during the cycle, so reordering is often
   needed. Keep every entry word for word; the release is not the place to edit entries.
4. Update the link references at the bottom of the file. Point `[Unreleased]` at the new version:
   `[Unreleased]: https://git.tillroll.example/tillroll/compare/vX.Y.Z...HEAD`. Then add a line for the new
   version directly below it: `[X.Y.Z]: https://git.tillroll.example/tillroll/compare/v<previous>...vX.Y.Z`,
   where `<previous>` is the last release.
5. Leave older releases, including their links, exactly as they are.

### 4.1 Example

Before:

```markdown
## [Unreleased]

### Fixed

- Something was fixed (OPS-1).

### Added

- Something was added (OPS-2).

## [1.4.2] - 2026-09-17
...
[Unreleased]: https://git.tillroll.example/tillroll/compare/v1.4.2...HEAD
[1.4.2]: https://git.tillroll.example/tillroll/compare/v1.4.1...v1.4.2
```

After (minor release, because of `Added`):

```markdown
## [Unreleased]

## [1.5.0] - 2026-10-01

### Added

- Something was added (OPS-2).

### Fixed

- Something was fixed (OPS-1).

## [1.4.2] - 2026-09-17
...
[Unreleased]: https://git.tillroll.example/tillroll/compare/v1.5.0...HEAD
[1.5.0]: https://git.tillroll.example/tillroll/compare/v1.4.2...v1.5.0
[1.4.2]: https://git.tillroll.example/tillroll/compare/v1.4.1...v1.4.2
```

## 5. The release metadata file

Every release has a file `release/X.Y.Z.toml` with these fields:

```toml
version = "X.Y.Z"
date = "YYYY-MM-DD"
bump = "minor"
previous = "1.4.2"
prerelease = false
migrations = ["0005"]
last_migration = "0005"
```

- `version`: the new version, exactly as in `pyproject.toml`.
- `date`: today's date, the same as in the changelog heading.
- `bump`: `major`, `minor` or `patch`, from section 2. For a release candidate, the bump of the final release.
- `previous`: the last non-candidate release, for example `1.4.2`.
- `prerelease`: `true` for a release candidate, otherwise `false`.
- `migrations`: the ids of the migrations added since the previous release, in order. Find them by comparing
  `db/migrations/manifest.json` with the `last_migration` field of the previous release's file: every id
  after that one is new. If there are none, use an empty list.
- `last_migration`: the highest migration id in the manifest now. If there are no new migrations, it is the
  same as in the previous release's file.

Never edit the release files of earlier releases; they are a record of what shipped.

## 6. What not to do

- Do not create git tags. CI creates the `vX.Y.Z` tag after the release pull request has been reviewed and
  merged; a tag created by hand points at an unreviewed commit and breaks the pipeline.
- Do not commit on the reviewer's behalf; leave the changes for review.
- Do not publish packages, deploy or notify anyone. That happens after the release is merged and is owned
  by operations.
- Do not change application code or migrations as part of cutting a release.

## 7. After the release is cut

For context only (none of this is part of cutting the release): the reviewer checks the version, the
changelog and the release file; once merged, CI tags the commit and builds the package; operations read the
release file, plan the deployment and announce it in the operations channel.

## 8. Troubleshooting

**The Unreleased section is empty.** There is nothing to release. Say so instead of cutting an empty release.

**A section heading is not one of the standard seven.** Fix the changelog in a separate change first; the
bump rule only knows the standard sections.

**The previous release was a release candidate.** `previous` is still the last non-candidate release, and the
next candidate number goes up by one (`rc2` after `rc1`).

**Migrations were added but are not in the manifest.** They are not part of the release. Raise it with the
author; do not add them to the manifest as part of the release.

## 9. Frequently asked questions

**Why not let a tool choose the version from commit messages?** Our commit messages are not consistent
enough, and the changelog is what operations read.

**Can I edit an entry's wording while cutting the release?** No. Raise it separately.

**Why the fixed section order?** Readers look for breaking changes and additions first; operations look for
security fixes last but always. A fixed order means nobody has to search.

## 10. Checklist

- [ ] Bump chosen from the Unreleased section headings: Breaking/Removed major; Added/Changed/Deprecated minor; Fixed/Security only patch.
- [ ] Release candidates use PEP 440 `X.Y.ZrcN` everywhere.
- [ ] Version updated in `pyproject.toml` and `src/tillroll/__init__.py`.
- [ ] Changelog: new empty `## [Unreleased]`; release heading `## [X.Y.Z] - YYYY-MM-DD`; sections in the fixed order; entries word for word.
- [ ] Changelog links: `[Unreleased]` compares from `vX.Y.Z`; new `[X.Y.Z]` line compares `v<previous>...vX.Y.Z`.
- [ ] `release/X.Y.Z.toml` with version, date, bump, previous, prerelease, migrations, last_migration.
- [ ] Older changelog entries and release files untouched.
- [ ] No git tag, no commit.
