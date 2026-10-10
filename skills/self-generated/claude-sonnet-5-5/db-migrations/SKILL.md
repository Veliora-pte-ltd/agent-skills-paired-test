---
name: db-migrations
description: Add a new SQLite schema migration to the tillroll repo (db/migrations/*.sql), including the manifest entry with sha256, the regenerated db/schema.sql, and the changelog line. Use when asked to add, change, or write a database migration, table, column, or index.
---

# Adding a database migration (tillroll)

Migrations are plain SQL files in `db/migrations/`, applied in the order listed in `db/migrations/manifest.json` (not by filename sort) by `src/tillroll/db.py`. `db/schema.sql` is a generated snapshot.

## Steps

1. **Pick the next id.** Look at the last entry in `manifest.json`; the new id is that number + 1, zero-padded to 4 digits (after `0005` comes `0006`).
2. **Create `db/migrations/<id>_<snake_case_summary>.sql`.** Existing names: `0002_add_orders_status`, `0003_index_orders_customer`, `0004_create_products`, `0005_add_customers_phone`. Use a verb-first summary (`add_`, `create_`, `index_`). Use exactly this layout:

   ```sql
   -- migration: 0006
   -- ticket: OPS-123
   -- reversible: yes
   -- +up
   ALTER TABLE customers ADD COLUMN example TEXT;
   -- +down
   ALTER TABLE customers DROP COLUMN example;
   ```

   - Header has three lines: `migration`, `ticket` (the OPS-nnn ticket; ask the user if unknown, don't invent one), `reversible`.
   - Both `-- +up` and `-- +down` markers are required; `split_migration` raises if either is missing. Don't use these strings in comments elsewhere.
   - `+down` must undo `+up` exactly, in reverse order for multiple statements (see 0001: drops `orders` before `customers`). Set `reversible: yes` only if that is true.
   - Conventions seen in the schema: `id INTEGER PRIMARY KEY`; money as integer `*_minor` columns; timestamps as `created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))`; foreign keys via `REFERENCES table (id)`; indexes named `ix_<table>__<column>`.
   - `ALTER TABLE ... ADD COLUMN` on existing tables needs a `DEFAULT` if `NOT NULL` (see 0002), or must be nullable (see 0005).
3. **Never edit an applied migration.** The manifest pins each file's hash, so changes to existing files go in a new migration.
4. **Register it in `manifest.json`.** Append (at the end) an entry with the sha256 of the final file contents, and compute it only after the SQL is final:

   ```bash
   sha256sum db/migrations/0006_<name>.sql
   ```

   ```json
   {
     "id": "0006",
     "file": "0006_<name>.sql",
     "sha256": "<64 hex chars>"
   }
   ```

   Keep the 2-space JSON indentation and add a comma after the previous entry. Any later edit to the SQL file means recomputing the hash.
5. **Regenerate the schema snapshot; don't hand-edit it:**

   ```bash
   PYTHONPATH=src python3 -m tillroll.db dump-schema
   ```

   This rewrites `db/schema.sql` from an in-memory database with all migrations applied. Commit the result (columns added via ALTER appear as `, col ...` at the end of the CREATE TABLE; that is expected).
6. **Verify:**

   ```bash
   python -m pytest
   ```

   `tests/test_orders.py::test_migrations_apply` applies every migration on an in-memory DB. Also check the down section runs: apply up on a scratch sqlite connection, then `executescript` the down SQL from `db.split_migration`. Don't leave `*.sqlite3` files around (git-ignored).
7. **Changelog.** Add a line under `## [Unreleased]` in `CHANGELOG.md`, in the right subsection (`### Added` / `### Changed` / `### Fixed`), in the form `- Optional phone number on customers (OPS-412).` Reference the ticket id.

## Do not touch

- `release/*.toml` and the version in `pyproject.toml`: these are written at release time. Release files list the migration ids shipped in that release (`migrations`) and `last_migration`; past migration commits did not modify them.
- Previously committed migration files and their manifest hashes.

## Commit

Past commits take the form `Migration 0005: add customers phone (OPS-412)`, containing the migration file, `manifest.json`, and `db/schema.sql` together. The changelog entry has been committed separately ("Changelog entries for unreleased work"); follow the user's preference if they want it in the same commit.
