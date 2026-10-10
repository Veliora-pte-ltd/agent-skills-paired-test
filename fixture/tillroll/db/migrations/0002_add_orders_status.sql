-- migration: 0002
-- ticket: OPS-117
-- reversible: yes
-- +up
ALTER TABLE orders ADD COLUMN status TEXT NOT NULL DEFAULT 'pending';
-- +down
ALTER TABLE orders DROP COLUMN status;
