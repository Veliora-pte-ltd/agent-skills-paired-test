"""Reference solutions, used to check that every verifier can pass (oracle run)
and that an untouched repository fails. Run: python oracle.py"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from tasks import TASKS, prepare, CREATED_AT
from verify import verify

MIG_SQL = {
    "mig-01-phone": ("add_customers_phone", "ALTER TABLE customers ADD COLUMN phone TEXT;",
                     "ALTER TABLE customers DROP COLUMN phone;"),
    "mig-02-channel": ("add_orders_channel", "ALTER TABLE orders ADD COLUMN channel TEXT NOT NULL DEFAULT 'web';",
                       "ALTER TABLE orders DROP COLUMN channel;"),
    "mig-03-refunds": ("create_refunds",
                       "CREATE TABLE refunds (\n    id INTEGER PRIMARY KEY,\n    order_id INTEGER NOT NULL REFERENCES orders (id),\n"
                       "    amount_minor INTEGER NOT NULL,\n    reason TEXT,\n    " + CREATED_AT + "\n);\n"
                       "CREATE INDEX ix_refunds__order_id ON refunds (order_id);",
                       "DROP INDEX ix_refunds__order_id;\nDROP TABLE refunds;"),
    "mig-04-created-index": ("index_orders_created_at", "CREATE INDEX ix_orders__created_at ON orders (created_at);",
                             "DROP INDEX ix_orders__created_at;"),
    "mig-05-sku": ("add_products_sku", "ALTER TABLE products ADD COLUMN sku TEXT;\n"
                   "CREATE UNIQUE INDEX ux_products__sku ON products (sku);",
                   "DROP INDEX ux_products__sku;\nALTER TABLE products DROP COLUMN sku;"),
    "mig-06-discount": ("add_orders_discount",
                        "ALTER TABLE orders ADD COLUMN discount_minor INTEGER NOT NULL DEFAULT 0;",
                        "ALTER TABLE orders DROP COLUMN discount_minor;"),
}
ORDER = ["Breaking", "Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"]


def solve_migration(task, wd: Path) -> None:
    slug, up, down = MIG_SQL[task.id]
    mig = wd / "db/migrations"
    n = len(list(mig.glob("*.sql"))) + 1
    f = mig / f"{n:04d}_{slug}.sql"
    f.write_text(f"-- migration: {n:04d}\n-- ticket: {task.expected['ticket']}\n-- reversible: yes\n"
                 f"-- +up\n{up}\n-- +down\n{down}\n")
    man = json.loads((mig / "manifest.json").read_text())
    man["migrations"].append({"id": f"{n:04d}", "file": f.name, "sha256": hashlib.sha256(f.read_bytes()).hexdigest()})
    (mig / "manifest.json").write_text(json.dumps(man, indent=2) + "\n")
    subprocess.run(["python3", "-m", "tillroll.db", "dump-schema"], cwd=wd, check=True,
                   env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin"}, capture_output=True)


def solve_release(task, wd: Path) -> None:
    e, v, today = task.expected, task.expected["version"], dt.date.today().isoformat()
    for rel, pat in (("pyproject.toml", r'(?m)^version = ".*"'), ("src/tillroll/__init__.py", r'__version__ = ".*"')):
        p = wd / rel
        repl = f'version = "{v}"' if rel == "pyproject.toml" else f'__version__ = "{v}"'
        p.write_text(re.sub(pat, repl, p.read_text(), count=1))
    cl = (wd / "CHANGELOG.md").read_text()
    head, rest = cl.split("## [Unreleased]\n", 1)
    unrel, older = rest.split("\n## [1.4.2]", 1)
    secs = {}
    for block in re.split(r"(?m)^### ", unrel.strip())[1:]:
        name, body = block.split("\n", 1)
        secs[name.strip()] = body.strip()
    body = "\n\n".join(f"### {s}\n\n{secs[s]}" for s in ORDER if s in secs)
    older_text = "## [1.4.2]" + older
    older_text = older_text.replace(
        "[Unreleased]: https://git.tillroll.example/tillroll/compare/v1.4.2...HEAD",
        f"[Unreleased]: https://git.tillroll.example/tillroll/compare/v{v}...HEAD\n"
        f"[{v}]: https://git.tillroll.example/tillroll/compare/v1.4.2...v{v}")
    (wd / "CHANGELOG.md").write_text(f"{head}## [Unreleased]\n\n## [{v}] - {today}\n\n{body}\n\n{older_text}")
    migs = ", ".join(f'"{m}"' for m in e["migrations"])
    (wd / "release" / f"{v}.toml").write_text(
        f'version = "{v}"\ndate = "{today}"\nbump = "{e["bump"]}"\nprevious = "{e["previous"]}"\n'
        f'prerelease = {str(e["prerelease"]).lower()}\nmigrations = [{migs}]\nlast_migration = "{e["last_migration"]}"\n')


def main() -> int:
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        for tid, task in TASKS.items():
            base, wd, noop = Path(tmp, tid, "base"), Path(tmp, tid, "wd"), Path(tmp, tid, "noop")
            for d in (base, wd, noop):
                prepare(task, d)
            (solve_migration if task.family == "migration" else solve_release)(task, wd)
            res = verify(task, wd, base)
            fails = [c for c in res if not c[1]]
            noop_pass = all(c[1] for c in verify(task, noop, base))
            print(f"{tid:24s} oracle {'PASS' if not fails else 'FAIL'} ({len(res)} checks)  no-op {'PASS(!)' if noop_pass else 'fail'}")
            for c in fails:
                print("    ", c)
            bad += bool(fails) + noop_pass
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
