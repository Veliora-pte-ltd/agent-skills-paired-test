---
name: db-migrations
description: Adds or changes the tillroll database schema by writing a new SQL migration in db/migrations. Use when a task adds, removes or alters a table, column or index, or mentions a migration or schema change. Not for application code that leaves the schema alone.
---

# Adding a tillroll migration

## Fast path

1. Number: highest `NNNN` in `db/migrations/` plus one. File: `db/migrations/NNNN_<slug>.sql`, slug in lower-case snake_case, at most 40 characters.
2. The file starts with exactly these three header lines, followed by the two sections:

   ```sql
   -- migration: NNNN
   -- ticket: OPS-<number>
   -- reversible: yes
   -- +up
   ...
   -- +down
   ...
   ```

3. `-- +down` must undo `-- +up` exactly: drop what you created, in reverse order.
4. Append an entry to `db/migrations/manifest.json`, keeping the existing entries as they are:
   `{"id": "NNNN", "file": "<file name>", "sha256": "<sha256 of the file bytes>"}`.
   Hash the file only once its content is final: `sha256sum db/migrations/NNNN_<slug>.sql`.
5. Regenerate the schema snapshot: `PYTHONPATH=src python3 -m tillroll.db dump-schema` (writes `db/schema.sql`). Never edit `schema.sql` by hand.
6. Check: `PYTHONPATH=src python3 -m pytest -q`.

## Rules

- Never edit an existing migration. Always add a new one. One migration per ticket.
- A new column on an existing table is nullable, or `NOT NULL` with a `DEFAULT`.
- Money is an `INTEGER` in minor units (pence) and the column name ends in `_minor`, e.g. `amount_minor`.
- Every new table has `created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))`.
- Index names: `ix_<table>__<column>`; unique indexes `ux_<table>__<column>` (two underscores before the column).
- SQLite cannot add a `UNIQUE` column with `ALTER TABLE`: add the column, then create a unique index.

## Out of scope

Backfilling data in large tables, and irreversible changes. Say so instead of guessing.
