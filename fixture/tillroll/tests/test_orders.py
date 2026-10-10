import sqlite3

from tillroll import db
from tillroll.orders import Order, order_total


def test_order_total():
    assert order_total([199, 1, 300]) == 500


def test_total_display():
    assert Order(1, 1, 1234).total_display() == "GBP 12.34"


def test_migrations_apply():
    conn = sqlite3.connect(":memory:")
    db.migrate(conn)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"customers", "orders", "products"} <= tables
