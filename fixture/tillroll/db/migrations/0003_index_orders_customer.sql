-- migration: 0003
-- ticket: OPS-140
-- reversible: yes
-- +up
CREATE INDEX ix_orders__customer_id ON orders (customer_id);
-- +down
DROP INDEX ix_orders__customer_id;
