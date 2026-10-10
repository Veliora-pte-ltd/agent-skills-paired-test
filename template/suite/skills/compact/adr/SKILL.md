---
name: adr
description: Write an architecture decision record (ADR) for example-service. Use when someone asks to record, write up or document a technical decision. Not for editing or accepting an existing ADR.
---

# Writing an ADR in example-service

## Fast path

1. Take the next number after the highest file in `docs/adr/` (four digits, e.g. `0003`).
2. Create `docs/adr/NNNN-short-title-in-kebab-case.md`:

   ```markdown
   # N. Title in sentence case

   Date: YYYY-MM-DD (today)
   Status: Proposed

   ## Context
   ## Decision
   ## Consequences
   ```

3. Add a row to the table in `docs/adr/README.md`: `| [NNNN](file.md) | Title | Proposed |`.

## Rules that cannot be inferred from the code

- A new ADR is always `Status: Proposed`. Only the architecture review marks it Accepted.
- Never edit an existing ADR. If a decision replaces an old one, say so in the new ADR's Context.

## Out of scope

Accepting, superseding or deleting ADRs: ask the architecture review instead of changing files.
