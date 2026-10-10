---
name: db-migrations
description: Add a new SQLite database migration to the tillroll repo following its conventions (numbered SQL file with header and +up/+down sections, manifest.json entry with sha256, regenerated db/schema.sql, changelog entry). Use when asked to change the database schema, e.g. add/alter/drop a table, column or index.
---

# Adding a database migration (tillroll)

Migrations are plain SQL files in `db/migrations/`, applied to SQLite in the order listed in `db/migrations/manifest.json` (see `src/tillroll/db.py`). The file name does not determine order; the manifest does. Applied migrations are immutable.

## Steps

1. **Find the next number.** Look at the last entry in `db/migrations/manifest.json` and add 1. IDs are zero-padded to 4 digits (`0006`, ...).
2. **Get the ticket ID** (format `OPS-123`) from the user or the task. If none is given, ask. Don't invent one.
3. **Create `db/migrations/<id>_<snake_case_description>.sql`.** Names are verb-first and descriptive: `add_orders_status`, `index_orders_customer`, `create_products`, `add_customers_phone`. Use exactly this layout:

   ```sql
   -- migration: 0006
   -- ticket: OPS-123
   -- reversible: yes
   -- +up
   ALTER TABLE customers ADD COLUMN example TEXT;
   -- +down
   ALTER TABLE customers DROP COLUMN example;
   ```

   - The header has these three lines, in this order, then `-- +up`, then `-- +down`. `split_migration` raises if either marker is missing.
   - Every existing migration has a working `-- +down` that exactly undoes `-- +up`, in reverse order (e.g. 0001 drops `orders` before `customers`). Write one, and keep `reversible: yes`.
   - Don't put the markers `-- +up` or `-- +down` anywhere else in the file, including comments.
   - End the file with a newline.
4. **Follow the schema conventions** seen in existing migrations:
   - Money is stored as integer minor units in `*_minor` columns (`total_minor`, `price_minor`). Currency is a `TEXT` column.
   - Primary keys are `id INTEGER PRIMARY KEY`.
   - Timestamps are `created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))`.
   - Foreign keys are written inline: `customer_id INTEGER NOT NULL REFERENCES customers (id)`.
   - Index names are `ix_<table>__<column>`, e.g. `ix_orders__customer_id`.
   - Adding a column to an existing table: use `ALTER TABLE ... ADD COLUMN`. A `NOT NULL` column needs a `DEFAULT` (like `status`); otherwise make it nullable (like `phone`).
   - One logical change per migration.
5. **Add the manifest entry.** Append to the `migrations` array in `db/migrations/manifest.json` (2-space indentation, same key order: `id`, `file`, `sha256`):

   ```json
   {
     "id": "0006",
     "file": "0006_add_example.sql",
     "sha256": "<hash>"
   }
   ```

   The hash is the SHA-256 of the migration file's exact bytes: `sha256sum db/migrations/0006_add_example.sql`. Compute it last, after the SQL is final. Any later edit to the file changes the hash, so recompute it.
6. **Regenerate the schema snapshot.** Do not edit `db/schema.sql` by hand. From the repo root run:

   ```bash
   PYTHONPATH=src python3 -m tillroll.db dump-schema
   ```

   Include the resulting `db/schema.sql` diff in the same change. (`ALTER TABLE ADD COLUMN` shows up as `, col ...` appended to the original `CREATE TABLE` in the dump. That is expected.)
7. **Add a changelog entry** under `## [Unreleased]` in `CHANGELOG.md`, in the matching subsection (`### Added`, `### Changed`, `### Fixed`; create it if missing). Write one line ending with the ticket, e.g. `- Optional phone number on customers (OPS-412).`
8. **Verify:**
   - `python -m pytest` passes. `test_migrations_apply` applies all the migrations to an in-memory database. If you add a new table, consider adding it to that test's expected set in `tests/test_orders.py`.
   - Check the down migration too. Run `split_migration` on your file (`from tillroll.db import split_migration`), then run the up SQL and the down SQL in sequence against a database that has the earlier migrations applied.
   - Check that every `sha256` in the manifest matches its file.

## Don't

- Don't edit or renumber a migration that is already in the manifest. Add a new migration to fix a mistake.
- Don't touch `release/*.toml`, the `version` in `pyproject.toml` or the version headings in `CHANGELOG.md`. Those belong to release commits (`release/<version>.toml` lists the `migrations` shipped in that release and the `last_migration`). Migration commits leave them alone.
- Don't run `python -m tillroll.db migrate` against a real database file as a test. Use `:memory:` or a throwaway `*.sqlite3` (git-ignored).

## Commit

The previous migration commit is the model: one commit with the title `Migration 0006: <short description> (OPS-123)`. It contains the SQL file, the manifest change and the regenerated `db/schema.sql`. (In history, the 0005 changelog entry was added in a separate later commit, so putting it in the same commit is fine but not required.)
