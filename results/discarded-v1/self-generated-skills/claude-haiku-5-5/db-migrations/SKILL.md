---
name: db-migrations
description: Add a new SQLite schema migration to the tillroll repo following its conventions - numbered SQL file with +up/+down sections, manifest.json entry with sha256, regenerated db/schema.sql, and an Unreleased changelog entry. Use when the user asks to add, change, or drop a table, column, or index, or to write any database migration in this repository.
---

# Adding a database migration (tillroll)

Migrations are plain SQLite SQL files in `db/migrations/`, applied in the order listed in `db/migrations/manifest.json`. A single change touches four places: the migration file, the manifest, the generated schema, and the changelog. Do all four in the same change.

Run commands from the repository root.

## 1. Pick the next id

Take the highest `id` in `db/migrations/manifest.json` and add 1, zero-padded to four digits. At the time of writing the highest is `0005`, so the next is `0006`. Do not reuse or renumber existing ids.

## 2. Name the file

Create `db/migrations/NNNN_<snake_case_summary>.sql`. The summary describes the change:

| Existing file | Kind of change |
|---|---|
| `0001_initial.sql` | create several tables |
| `0002_add_orders_status.sql` | add a column |
| `0003_index_orders_customer.sql` | add an index |
| `0004_create_products.sql` | create a table |
| `0005_add_customers_phone.sql` | add a column |

## 3. Write the file

Use exactly this header and section layout:

```sql
-- migration: 0006
-- ticket: OPS-NNN
-- reversible: yes
-- +up
ALTER TABLE customers ADD COLUMN loyalty_tier TEXT;
-- +down
ALTER TABLE customers DROP COLUMN loyalty_tier;
```

- `-- migration:` is the id without a file suffix. Keep it equal to the number in the file name.
- `-- ticket:` is the tracking ticket (`OPS-NNN`). Every existing migration has one.
- `-- reversible:` is `yes` or `no`. Every existing migration is `yes`.
- Both `-- +up` and `-- +down` markers are required. `split_migration` in `src/tillroll/db.py` raises an error if either is missing. Put the forward SQL between `+up` and `+down`, and the reverse SQL after `+down`.

### SQL conventions seen in the repo

- SQLite dialect. Use `INTEGER PRIMARY KEY` for `id`.
- Timestamps use this exact default:
  `created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))`
- Money is stored as integer minor units in columns named `*_minor` (`total_minor`, `price_minor`). Do not use floats or `REAL` for money.
- Columns are snake_case. Foreign keys are `<table_singular>_id INTEGER NOT NULL REFERENCES <table> (id)`.
- Indexes are named `ix_<table>__<column>` with a double underscore before the column, for example `ix_orders__customer_id`.
- A new `NOT NULL` column on an existing table needs a `DEFAULT`. `0002` uses `DEFAULT 'pending'` for this reason. An optional column is a plain nullable `ADD COLUMN`, as in `0005`.
- No existing migration contains `BEGIN` or `COMMIT`. Leave transaction handling out of the file. `migrate()` runs each file with `executescript`.

### Writing the `+down` section

- Reverse the `+up` changes: `DROP TABLE`, `DROP INDEX`, or `ALTER TABLE ... DROP COLUMN`.
- When several tables have foreign keys between them, drop the referencing table first. `0001_initial.sql` drops `orders` before `customers` for this reason.
- `DROP COLUMN` needs SQLite 3.35 or later.
- Nothing in the repo runs `+down` sections. They document the reverse path and are not executed by the tooling. You can check one by hand against a scratch database (see step 7).
- If a change cannot be reversed (for example, it drops data), set `-- reversible: no`. The `+down` section must still exist, because the parser requires it. Put a SQL comment explaining why there is no safe reverse. No existing migration does this, so this is a convention inferred from the header format, not an established precedent.

## 4. Never edit an applied migration

Existing migration files are never changed. The git history for `db/migrations/` only adds new files. To correct a mistake in a migration that has been merged, add a new migration that fixes it. Do not edit the old file, because its sha256 in the manifest would no longer match.

## 5. Add the manifest entry

Append an object to the `migrations` array in `db/migrations/manifest.json`. Keep it at the end, because `migrate()` applies files in manifest order. Use the same two-space indent as the other entries:

```json
    {
      "id": "0006",
      "file": "0006_add_customers_loyalty_tier.sql",
      "sha256": "<output of sha256sum for the file>"
    }
```

Compute the hash with:

```bash
sha256sum db/migrations/0006_add_customers_loyalty_tier.sql
```

Use the first field of the output. The hash is over the file's exact bytes, so compute it after the file is final. Nothing in the code checks the hash at present, but it is recorded for every migration, so record it for yours.

## 6. Regenerate the schema

`db/schema.sql` is generated and marked "do not edit by hand". Regenerate it from the repository root:

```bash
PYTHONPATH=src python3 -m tillroll.db dump-schema
```

This applies every migration in the manifest to an in-memory database and writes `db/schema.sql`. Commit the regenerated file. Do not edit it by hand. The `phone` column appears in the `customers` definition in `schema.sql` after the migration is applied, not as a separate statement.

## 7. Verify

1. Run the test suite:
   ```bash
   python -m pytest
   ```
   `tests/test_orders.py::test_migrations_apply` applies every migration from the manifest to an in-memory database. A broken or misnumbered migration fails here.
2. Apply the migrations to a scratch database. The `*.sqlite3` pattern is git-ignored, but you can also use a `/tmp` path:
   ```bash
   PYTHONPATH=src python3 -m tillroll.db migrate /tmp/scratch.sqlite3
   ```
   The README shows the same command without `PYTHONPATH=src`. That form only works if the package is installed.
3. If the change is reversible, you can check the `+down` section against the scratch database with `sqlite3`. Run the `+up` SQL, then the `+down` SQL, and confirm the schema matches the state before the migration. Do not commit the scratch database.

## 8. Add a changelog entry

Under `## [Unreleased]` in `CHANGELOG.md`, add a bullet to the right subsection (`### Added`, `### Changed`, or `### Fixed`). Describe the change in plain language, not in SQL, and end it with the ticket in parentheses. Examples from the file:

- `Optional phone number on customers (OPS-412).`
- `Index on orders by customer (OPS-140).`

Create the `### Added`, `### Changed`, or `### Fixed` subsection if it does not already exist under Unreleased, and keep the usual ordering.

## 9. Do not touch release files for unreleased work

`release/<version>.toml` is written when a release is cut, not when a migration is added. Leave the release files alone while the change is unreleased. For reference, a release file records:

- `migrations`: the ids introduced in that release, for example `["0004"]` in `release/1.4.2.toml`
- `last_migration`: the highest id at the time of release

Release mechanics (version bump, tagging) are outside this skill.

## 10. Commit

Put the migration file, `db/migrations/manifest.json`, `db/schema.sql`, and the `CHANGELOG.md` entry in one commit. Use the subject format from the repo's history:

```
Migration 0006: add customers loyalty tier (OPS-NNN)
```

## Checklist

- [ ] Id is the next number in the manifest, zero-padded to four digits.
- [ ] File is `db/migrations/NNNN_<summary>.sql` with `migration`, `ticket`, and `reversible` header lines.
- [ ] Both `-- +up` and `-- +down` sections are present.
- [ ] Money is in `*_minor INTEGER` columns; timestamps use the standard `created_at` default.
- [ ] New `NOT NULL` columns on existing tables have a `DEFAULT`.
- [ ] No existing migration file was edited.
- [ ] Manifest entry appended, with the `sha256sum` of the final file.
- [ ] `db/schema.sql` regenerated with `dump-schema`, not edited by hand.
- [ ] `python -m pytest` passes.
- [ ] `CHANGELOG.md` has a bullet under `[Unreleased]`.
- [ ] `release/*.toml` and `pyproject.toml` are unchanged.
