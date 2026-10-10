---
name: db-migrations
description: Adds or changes the tillroll database schema by writing a new SQL migration in db/migrations. Use when a task adds, removes or alters a table, column or index, or mentions a migration or schema change. Not for application code that leaves the schema alone.
---

# tillroll database migrations: the complete guide

This guide describes how the tillroll team changes the database schema. It covers the background to the
migration system, the file format, naming, the manifest, the schema snapshot, reversibility, data types,
indexes, review, troubleshooting and a set of worked examples. It is long because it tries to answer
every question that has come up in review over the last two years. If you only need the essentials, the
"Checklist" section near the end lists every rule in one place.

## 1. Background

tillroll stores its data in SQLite. Early versions of the service created tables from Python code at
start-up, which made it hard to see what the schema was at any point in history and impossible to roll a
change back cleanly. In version 1.0 the team moved to plain SQL migration files that are applied in order.
We deliberately did not adopt a migration framework: the files are simple enough to read in review, the
applier is about forty lines of Python (`src/tillroll/db.py`), and there is nothing to upgrade.

The trade-off is that the conventions live in people's heads rather than in a framework, which is why this
guide exists. Most review comments on schema changes over the past year were about the conventions below,
not about the SQL itself.

### 1.1 How migrations are applied

`src/tillroll/db.py` reads `db/migrations/manifest.json`, takes the files in the order they are listed,
splits each file at the `-- +up` and `-- +down` markers and runs the `up` part with `executescript`. The
`down` part is used by the operations team when they need to roll a release back, and by CI, which applies
every migration up and then down again to check that the schema returns to where it started.

Because the manifest drives the order, a migration file that is not listed in the manifest is never applied.
This has caught people out more than once: a file was added, the tests passed locally because the developer
had created the table by hand, and the change silently did nothing in production.

### 1.2 Who reviews schema changes

Any engineer can write a migration. Every migration is reviewed by one other engineer, and changes to
tables with more than a million rows are also reviewed by operations. The reviewer checks the conventions
in this guide, that the change is reversible, and that the snapshot has been regenerated.

## 2. Where migrations live and how they are named

All migrations live in `db/migrations/`. Each file is named `NNNN_<slug>.sql`:

- `NNNN` is a four-digit, zero-padded sequence number. Take the highest number currently in
  `db/migrations/` and add one. Numbers are never reused, even if a migration is later superseded.
- `<slug>` is a short description in lower-case snake_case, at most 40 characters, for example
  `add_customers_phone` or `create_refunds`. Avoid dates and ticket numbers in the slug; the ticket goes in
  the header.

Two people occasionally pick the same number on parallel branches. Whoever merges second renumbers their
migration (file name, header line and manifest entry) before merging. Do not "fix" this by editing the
migration that has already been merged.

## 3. The file format

Every migration file starts with exactly three header lines, followed by an `up` section and a `down`
section. The header lines are read by our release tooling and by a dashboard the operations team uses, so
their exact spelling matters: no extra spaces, no capitals, and nothing before them.

```sql
-- migration: NNNN
-- ticket: OPS-<number>
-- reversible: yes
-- +up
<SQL that makes the change>
-- +down
<SQL that undoes the change>
```

- `-- migration:` repeats the four-digit number from the file name.
- `-- ticket:` is the ticket in our tracker that asked for the change, in the form `OPS-412`.
- `-- reversible: yes` states that the `down` section restores the previous schema exactly. Every
  migration you write as part of normal work should be reversible (see section 6).
- `-- +up` and `-- +down` must each appear exactly once, in that order.

Comments inside the sections are welcome, especially where the reason for a choice is not obvious.

## 4. The manifest

`db/migrations/manifest.json` lists every migration in the order it is applied. When you add a migration,
append one entry to the end of the list and leave the existing entries exactly as they are:

```json
{"id": "NNNN", "file": "NNNN_<slug>.sql", "sha256": "<sha256 of the file bytes>"}
```

The `sha256` field is the SHA-256 hash of the migration file's bytes, as a lower-case hex string. CI
recomputes the hash of every file and fails if any differ; the operations team relies on this to know that
the file they reviewed is the file that ran. Compute the hash only after the file's content is final, for
example with `sha256sum db/migrations/NNNN_<slug>.sql`. If you edit the file afterwards, recompute it.

Historically the hash was added after an incident in which a migration was edited after it had been applied
in staging, so staging and production ended up with different schemas. That incident is also the reason for
the rule in the next section.

## 5. Never edit an existing migration

Once a migration has been merged, it is history. Never edit it, even to fix a typo in a comment, because
its hash is recorded and because environments that have already run it will not run it again. If a previous
migration was wrong, write a new migration that corrects it. Always add a new file; one migration per
ticket keeps review and rollback simple.

## 6. Reversibility

The `down` section must undo the `up` section exactly, so that applying `up` and then `down` leaves the
schema identical to how it was before. In practice:

- If `up` creates a table, `down` drops it.
- If `up` adds a column, `down` drops that column (`ALTER TABLE ... DROP COLUMN ...`; SQLite has supported
  this since 3.35).
- If `up` creates an index, `down` drops that index.
- If `up` does several things, `down` undoes them in reverse order: drop indexes before the columns or
  tables they cover.

CI checks reversibility by comparing the structure of every table and index before and after the round trip.

Irreversible changes (for example dropping a column whose data cannot be recreated) and backfills of large
tables are outside normal work. They need a plan agreed with operations, so if a task seems to require one,
say so instead of guessing.

## 7. Columns and data types

### 7.1 Adding a column to an existing table

A new column on an existing table must be nullable, or `NOT NULL` with a `DEFAULT`. SQLite refuses to add a
`NOT NULL` column without a default to a table that has rows, and even where it would work, existing rows
need a sensible value. Choose the default that matches what the business says existing records should
have; if the ticket says existing orders have no discount, the default is `0`.

### 7.2 Money

Money is always stored as an `INTEGER` number of minor units (pence for GBP), never as `REAL` or `TEXT`,
and the column name ends in `_minor`, for example `amount_minor`, `price_minor` or `discount_minor`. The
existing `orders.total_minor` and `products.price_minor` columns follow this rule. Floating-point money
caused a rounding bug in 2024 that took a week to reconcile; the suffix makes the unit obvious in queries.

### 7.3 Timestamps on new tables

Every new table has a `created_at` column defined exactly like this:

```sql
created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
```

This stores an ISO 8601 UTC timestamp with milliseconds. Do not use `CURRENT_TIMESTAMP`, which has a
different format and no time zone marker, and do not leave the column nullable.

### 7.4 Foreign keys

Reference the parent table explicitly, for example `order_id INTEGER NOT NULL REFERENCES orders (id)`.
Name foreign key columns `<singular parent>_id`.

### 7.5 Text

Use `TEXT` for strings. SQLite ignores length limits in `VARCHAR(n)`, so they only mislead readers.

## 8. Indexes

Index names follow a fixed pattern so that they are easy to find in query plans:

- an ordinary index is `ix_<table>__<column>`, for example `ix_orders__customer_id`;
- a unique index is `ux_<table>__<column>`, for example `ux_products__sku`.

Note the two underscores between the table and the column. For an index on several columns, join the column
names with a single underscore after the double underscore.

SQLite cannot add a column with a `UNIQUE` constraint through `ALTER TABLE`. To make a new column unique,
add the column first, then create a unique index on it in the same migration. Remember to drop the index
before the column in `down`.

## 9. The schema snapshot

`db/schema.sql` is a snapshot of the full schema after all migrations have run. Reviewers read it to see
the effect of a change without replaying every migration in their heads, and the diff of `schema.sql` in a
pull request is often the most useful part of the review.

Regenerate it after adding a migration:

```bash
PYTHONPATH=src python3 -m tillroll.db dump-schema
```

This applies every migration in the manifest to an in-memory database and writes `db/schema.sql`. Never edit
`schema.sql` by hand: CI regenerates it and fails if the committed file differs.

## 10. Testing your migration

Run the test suite:

```bash
PYTHONPATH=src python3 -m pytest -q
```

It applies all migrations to an in-memory database. To try your migration against a file you can inspect:

```bash
PYTHONPATH=src python3 -m tillroll.db migrate /tmp/check.sqlite3
sqlite3 /tmp/check.sqlite3 '.schema'
```

## 11. Review checklist (what reviewers look for)

Reviewers usually check, in this order: the file name and number; the three header lines; that `up` does what
the ticket asks and nothing more; that `down` undoes it exactly; data types and naming (money, `created_at`,
index names); the manifest entry and hash; and the regenerated snapshot.

## 12. Troubleshooting

**"Cannot add a NOT NULL column with default value NULL".** Add a `DEFAULT`, or make the column nullable
(section 7.1).

**"Cannot add a UNIQUE column".** Add the column, then a unique index (section 8).

**CI says the hash does not match.** You edited the migration after computing its hash. Recompute it and
update the manifest entry. If the file is an older migration, revert your edit instead (section 5).

**CI says the schema snapshot is out of date.** Run the dump-schema command (section 9) and commit the result.

**My migration does not run.** Check that it is listed in the manifest (section 1.1).

**`ModuleNotFoundError: No module named 'tillroll'`.** Run commands from the repository root with
`PYTHONPATH=src`.

## 13. Worked examples

### 13.1 Adding an optional column

Ticket OPS-500 asks for an optional loyalty number on customers. With migrations up to 0004 present:

`db/migrations/0005_add_customers_loyalty_number.sql`

```sql
-- migration: 0005
-- ticket: OPS-500
-- reversible: yes
-- +up
ALTER TABLE customers ADD COLUMN loyalty_number TEXT;
-- +down
ALTER TABLE customers DROP COLUMN loyalty_number;
```

Then append `{"id": "0005", "file": "0005_add_customers_loyalty_number.sql", "sha256": "..."}` to the
manifest and regenerate the snapshot.

### 13.2 Creating a table with money and an index

Ticket OPS-501 asks for gift cards linked to customers:

```sql
-- migration: 0005
-- ticket: OPS-501
-- reversible: yes
-- +up
CREATE TABLE gift_cards (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers (id),
    balance_minor INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX ix_gift_cards__customer_id ON gift_cards (customer_id);
-- +down
DROP INDEX ix_gift_cards__customer_id;
DROP TABLE gift_cards;
```

### 13.3 A unique column

Ticket OPS-502 asks for a unique external reference on orders:

```sql
-- +up
ALTER TABLE orders ADD COLUMN external_ref TEXT;
CREATE UNIQUE INDEX ux_orders__external_ref ON orders (external_ref);
-- +down
DROP INDEX ux_orders__external_ref;
ALTER TABLE orders DROP COLUMN external_ref;
```

## 14. Frequently asked questions

**Can I put two tickets in one migration?** No. One migration per ticket.

**Can I use a migration to insert reference data?** Small, fixed reference data is fine, with a `down` that
deletes it. Anything larger is a backfill and needs operations (section 6).

**Should the slug include the ticket number?** No, the ticket goes in the header.

**What if the highest number is used on another open branch?** Use the next number on yours; whoever merges
second renumbers (section 2).

## 15. Checklist

- [ ] New file `db/migrations/NNNN_<slug>.sql`, number = highest + 1, slug lower-case snake_case, at most 40 characters.
- [ ] Exactly three header lines: `-- migration: NNNN`, `-- ticket: OPS-<number>`, `-- reversible: yes`.
- [ ] `-- +up` then `-- +down`; `down` undoes `up` exactly, in reverse order.
- [ ] No existing migration edited.
- [ ] New columns on existing tables nullable or `NOT NULL` with `DEFAULT`.
- [ ] Money as `INTEGER` with a `_minor` suffix.
- [ ] New tables have the standard `created_at` column.
- [ ] Index names `ix_<table>__<column>` / `ux_<table>__<column>`.
- [ ] Manifest entry appended with the correct SHA-256.
- [ ] `db/schema.sql` regenerated with `PYTHONPATH=src python3 -m tillroll.db dump-schema`.
- [ ] Tests pass.
