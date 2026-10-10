# 2. Use SQLite for local storage

Date: 2026-09-14
Status: Accepted

## Context

The service needs durable storage on a single machine.

## Decision

Use SQLite, one database file per environment.

## Consequences

Backups are file copies. Concurrent writers are limited.
