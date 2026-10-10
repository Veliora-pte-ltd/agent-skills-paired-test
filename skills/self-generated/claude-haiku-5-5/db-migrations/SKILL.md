---
name: db-migrations
description: Add a new SQLite schema migration to the tillroll repo following its conventions (numbered SQL file with +up/+down sections, manifest.json entry, regenerated db/schema.sql, CHANGELOG entry, ticket reference). Use when the user asks to add, change, or drop a table, column, or index, or otherwise alter the database schema.
---

# Adding a database migration (tillroll)

Migrations are plain SQLite files applied in order by `src/tillroll/db.py`. The
order is defined only by `db/migrations/manifest.json`, not by directory listing.
Follow the steps below in order.

## 1. Pick the next number

- Look at the last entry in `db/migrations/manifest.json`. The new id is that
  number plus one, zero-padded to four digits (`0005` is the last today, so the
  next is `0006`).
- Do not renumber or reuse an existing id, even if a migration looks obsolete.

## 2. Name the file

`db/migrations/NNNN_<snake_case_summary>.sql`, where the summary is a short
verb phrase that matches the existing names:

- `0001_initial.sql`
- `0002_add_orders_status.sql`
- `0003_index_orders_customer.sql`
- `0004_create_products.sql`
- `0005_add_customers_phone.sql`

## 3. Write the file

Use this exact layout. The header is three comment lines, then an `+up` section,
then a `+down` section. `split_migration` requires both markers.

```sql
-- migration: 0006
-- ticket: OPS-NNN
-- reversible: yes
-- +up
ALTER TABLE customers ADD COLUMN loyalty_points INTEGER;
-- +down
ALTER TABLE customers DROP COLUMN loyalty_points;
```

Rules that the existing files follow:

- `ticket:` is the Jira-style ticket that justifies the change (`OPS-###`). Ask
  the user for it if they have not given one; do not invent one.
- `reversible: yes` is used by every migration so far, and each `+down` is the
  exact reverse of its `+up`. If a change cannot be reversed, do not guess at
  the convention: no existing file shows it, so state that in your final message
  and ask the user how to proceed.
- Keep `+down` in the reverse order of `+up` when there are several statements
  (`0001_initial.sql` drops `orders` before `customers`, because of the foreign
  key).
- Column and table style matches the existing schema:
  - `id INTEGER PRIMARY KEY` for new tables.
  - Money is stored as integer minor units with a `_minor` suffix
    (`total_minor`, `price_minor`), never as a float.
  - Timestamps are `TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))`
    with a `created_at` column.
  - Indexes are named `ix_<table>__<column>` (`ix_orders__customer_id`).
- Adding a `NOT NULL` column to a table that already has rows needs a `DEFAULT`
  (see `0002_add_orders_status.sql`). Otherwise make the new column nullable, as
  `0005_add_customers_phone.sql` does.
- `ALTER TABLE ... DROP COLUMN` is what the existing down sections use, so it is
  acceptable here. It needs SQLite 3.35 or newer.
- Do not edit a migration that has already shipped. Each entry in
  `manifest.json` carries a sha256 of its file, which means the file is meant to
  be fixed after it is recorded. Make a new migration instead.

## 4. Register it in the manifest

Add an entry to `db/migrations/manifest.json` at the end of the `migrations`
array:

```json
{
  "id": "0006",
  "file": "0006_add_customers_loyalty_points.sql",
  "sha256": "<output of: sha256sum db/migrations/0006_....sql>"
}
```

Compute the hash from the file as written. Do this after the file is final, since
any later edit changes the hash. Keep the JSON formatting (two-space indent) that
the file already uses.

## 5. Regenerate the schema snapshot

`db/schema.sql` is generated. Do not edit it by hand. Regenerate it with:

```bash
PYTHONPATH=src python3 -m tillroll.db dump-schema
```

This applies every migration to an in-memory database and writes the result to
`db/schema.sql`. Check the diff: it should show only the new change.

## 6. Verify

- Run the test suite: `python -m pytest`. `tests/test_orders.py::test_migrations_apply`
  applies all migrations to a fresh database.
- Apply to a scratch database outside the repo, for example
  `python -m tillroll.db migrate /tmp/check.sqlite3`. `*.sqlite3` is gitignored,
  but keep scratch files out of the repo regardless.
- The `+down` section is never executed by the code. To check it, run the up and
  down SQL by hand against a scratch SQLite database (up, then down, then confirm
  the schema matches the state before the migration).

## 7. Update the changelog

Add an entry under `## [Unreleased]` in `CHANGELOG.md`, in the matching subsection
(`### Added`, `### Changed`, or `### Fixed`). Use the same format as the existing
entries, ending with the ticket in parentheses:

```markdown
- Loyalty points on customers (OPS-NNN).
```

Do not add a new version section or a `release/*.toml` file. Those are created at
release time. The release files record which migrations shipped in each version
(`migrations = [...]`, `last_migration = "..."`), and the `[Unreleased]` section is
where unshipped work is listed.

## 8. Commit

Follow the history:

- Commit the migration in one commit with the `.sql` file, `manifest.json`, and
  the regenerated `db/schema.sql`. The subject is
  `Migration NNNN: <short summary> (OPS-NNN)`, as in
  `019a3a0 Migration 0005: add customers phone (OPS-412)`.
- The changelog entry was committed separately in the history
  (`e7f93a8 Changelog entries for unreleased work`). Either commit it separately
  as well, or include it, following what the user asks for.
- Only commit when the user asks you to. End the commit message with the
  attribution line required by the session.

## Checklist

- [ ] Next id is the manifest's last id plus one, four digits.
- [ ] File name is `NNNN_snake_case_summary.sql`.
- [ ] Header has `migration`, `ticket`, and `reversible`; both `-- +up` and `-- +down` are present.
- [ ] `+down` exactly reverses `+up`.
- [ ] Money is in `_minor` integers; new `NOT NULL` columns on existing tables have a default.
- [ ] Manifest entry added with the file's sha256.
- [ ] `db/schema.sql` regenerated with `dump-schema`, not hand-edited.
- [ ] `python -m pytest` passes.
- [ ] `CHANGELOG.md` `[Unreleased]` entry added with the ticket.
- [ ] No shipped migration was edited; no release file created.
