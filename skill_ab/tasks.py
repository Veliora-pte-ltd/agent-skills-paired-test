"""Task definitions for the skill A/B experiment.

Every task starts from the `fixture/tillroll` repository. Release tasks add
some unreleased history first (extra migrations and an `Unreleased`
changelog section). Prompts are written the way a developer would type
them: they never mention the conventions the skills describe.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE.parent / "fixture" / "tillroll"

CREATED_AT = "created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"


@dataclass(frozen=True)
class Task:
    id: str
    family: str  # "migration" or "release"
    prompt: str
    expected: dict
    extra_migrations: tuple = ()
    unreleased: str = ""
    work: tuple = ()  # code changes (ticket ids in CODE_CHANGES) committed after v1.4.2


# ---------------------------------------------------------------- migrations
MIGRATION_TASKS = [
    Task(
        "mig-01-phone", "migration",
        "Add a migration for ticket OPS-412: customers need an optional phone number column.",
        {"ticket": "OPS-412", "kind": "add_column", "table": "customers", "column_like": "phone",
         "nullable": True},
    ),
    Task(
        "mig-02-channel", "migration",
        "Ticket OPS-415: add a `channel` column to orders recording where the order came from. "
        "Existing and new orders should default to 'web'.",
        {"ticket": "OPS-415", "kind": "add_column", "table": "orders", "column": "channel",
         "default": "'web'"},
    ),
    Task(
        "mig-03-refunds", "migration",
        "Ticket OPS-420: we need to record refunds. Add a refunds table linked to orders, with the "
        "refunded amount and a free-text reason, and make it fast to look up the refunds for an order.",
        {"ticket": "OPS-420", "kind": "create_table", "table": "refunds", "fk": ("order_id", "orders"),
         "money_like": "amount", "index": ("ix_refunds__order_id", ["order_id"], False)},
    ),
    Task(
        "mig-04-created-index", "migration",
        "Ticket OPS-423: reports filter orders by creation date and they are slow. Add an index for that.",
        {"ticket": "OPS-423", "kind": "add_index", "table": "orders",
         "index": ("ix_orders__created_at", ["created_at"], False)},
    ),
    Task(
        "mig-05-sku", "migration",
        "Ticket OPS-431: products need a SKU. Add it as an optional column; SKUs must be unique.",
        {"ticket": "OPS-431", "kind": "add_column", "table": "products", "column": "sku",
         "nullable": True, "index": ("ux_products__sku", ["sku"], True)},
    ),
    Task(
        "mig-06-discount", "migration",
        "Ticket OPS-437: orders can now carry a discount amount. Add a column for it; existing orders "
        "have no discount.",
        {"ticket": "OPS-437", "kind": "add_column", "table": "orders", "money_like": "discount",
         "default": "0"},
    ),
]

# ------------------------------------------------------------------ releases
PHONE = ("add_customers_phone", "OPS-412",
         "ALTER TABLE customers ADD COLUMN phone TEXT;",
         "ALTER TABLE customers DROP COLUMN phone;")
CHANNEL = ("add_orders_channel", "OPS-415",
           "ALTER TABLE orders ADD COLUMN channel TEXT NOT NULL DEFAULT 'web';",
           "ALTER TABLE orders DROP COLUMN channel;")
CREATED_IDX = ("index_orders_created_at", "OPS-423",
               "CREATE INDEX ix_orders__created_at ON orders (created_at);",
               "DROP INDEX ix_orders__created_at;")

RELEASE_TASKS = [
    Task(
        "rel-01-patch", "release", "Cut the next release of tillroll.",
        {"version": "1.4.3", "bump": "patch", "previous": "1.4.2", "prerelease": False,
         "migrations": [], "last_migration": "0004", "sections": ["Fixed"]},
        unreleased="### Fixed\n\n- Currency codes are validated when an order is created (OPS-402).\n",
        work=("OPS-402",),
    ),
    Task(
        "rel-02-minor", "release", "Please prepare the next tillroll release.",
        {"version": "1.5.0", "bump": "minor", "previous": "1.4.2", "prerelease": False,
         "migrations": ["0005"], "last_migration": "0005", "sections": ["Added", "Fixed"]},
        extra_migrations=(PHONE,),
        unreleased=("### Added\n\n- Optional phone number on customers (OPS-412).\n\n"
                    "### Fixed\n\n- `order_total` rejects negative line amounts (OPS-409).\n"),
        work=("OPS-409",),
    ),
    Task(
        "rel-03-major", "release",
        "We're ready to ship what's in Unreleased. Prepare the release.",
        {"version": "2.0.0", "bump": "major", "previous": "1.4.2", "prerelease": False,
         "migrations": ["0005", "0006"], "last_migration": "0006", "sections": ["Added", "Removed"]},
        extra_migrations=(CHANNEL, CREATED_IDX),
        unreleased=("### Added\n\n- Order channel, defaulting to `web` (OPS-415).\n"
                    "- Index on orders by creation date (OPS-423).\n\n"
                    "### Removed\n\n- The deprecated `sum_lines` alias of `order_total` (OPS-377).\n"),
        work=("OPS-377",),
    ),
    Task(
        "rel-04-changed", "release", "Cut a release with the current unreleased changes.",
        {"version": "1.5.0", "bump": "minor", "previous": "1.4.2", "prerelease": False,
         "migrations": [], "last_migration": "0004", "sections": ["Changed"]},
        unreleased="### Changed\n\n- Order status values are normalised to lower case (OPS-421).\n",
        work=("OPS-421",),
    ),
    Task(
        "rel-05-rc", "release", "Cut the first release candidate for the next tillroll release.",
        {"version": "1.5.0rc1", "bump": "minor", "previous": "1.4.2", "prerelease": True,
         "migrations": ["0005"], "last_migration": "0005", "sections": ["Added"]},
        extra_migrations=(PHONE,),
        unreleased="### Added\n\n- Optional phone number on customers (OPS-412).\n",
    ),
    Task(
        "rel-06-security", "release", "Prepare the next release.",
        {"version": "1.4.3", "bump": "patch", "previous": "1.4.2", "prerelease": False,
         "migrations": [], "last_migration": "0004", "sections": ["Fixed", "Security"]},
        # deliberately out of canonical order: the skill says Fixed comes before Security
        unreleased=("### Security\n\n- Customer emails are no longer written to debug logs (OPS-433).\n\n"
                    "### Fixed\n\n- Discounted prices round half up to the nearest penny (OPS-429).\n"),
        work=("OPS-433", "OPS-429"),
    ),
]

TASKS = {t.id: t for t in MIGRATION_TASKS + RELEASE_TASKS}


# Small, real code changes behind the changelog entries, so that the history
# after v1.4.2 matches what the changelog claims.
def _append(path: str, code: str):
    def f(wd: Path) -> None:
        p = wd / path
        p.write_text((p.read_text() if p.exists() else "") + code)
    return f


def _replace(path: str, old: str, new: str):
    def f(wd: Path) -> None:
        p = wd / path
        text = p.read_text()
        assert old in text, (path, old)
        p.write_text(text.replace(old, new, 1))
    return f


CODE_CHANGES = {
    "OPS-402": ("Validate currency codes on order creation (OPS-402)", [
        _replace("src/tillroll/orders.py", "@dataclass(frozen=True)\nclass Order:",
                 'SUPPORTED_CURRENCIES = frozenset({"GBP", "EUR"})\n\n\n@dataclass(frozen=True)\nclass Order:'),
        _replace("src/tillroll/orders.py", "    def total_display(self) -> str:",
                 "    def __post_init__(self) -> None:\n"
                 "        if self.currency not in SUPPORTED_CURRENCIES:\n"
                 "            raise ValueError(f\"unsupported currency {self.currency!r}\")\n\n"
                 "    def total_display(self) -> str:"),
    ]),
    "OPS-409": ("Reject negative line amounts in order_total (OPS-409)", [
        _replace("src/tillroll/orders.py", "    return sum(line_amounts_minor)",
                 "    if any(a < 0 for a in line_amounts_minor):\n"
                 "        raise ValueError(\"line amounts must not be negative\")\n"
                 "    return sum(line_amounts_minor)"),
    ]),
    "OPS-377": ("Remove deprecated sum_lines alias (OPS-377)", [
        _replace("src/tillroll/orders.py", "\n\n# Deprecated alias kept for 1.x callers.\nsum_lines = order_total\n", "\n"),
    ]),
    "OPS-421": ("Normalise order status to lower case (OPS-421)", [
        _append("src/tillroll/orders.py",
                "\n\ndef normalise_status(status: str) -> str:\n"
                "    \"\"\"Order statuses are stored in lower case.\"\"\"\n"
                "    return status.strip().lower()\n"),
    ]),
    "OPS-433": ("Redact customer emails in debug logs (OPS-433)", [
        _append("src/tillroll/log.py",
                '"""Logging helpers."""\nfrom __future__ import annotations\n\nimport re\n\n'
                '_EMAIL = re.compile(r"[^@\\s]+@[^@\\s]+")\n\n\n'
                "def redact(message: str) -> str:\n"
                '    """Replace email addresses before a message is logged."""\n'
                '    return _EMAIL.sub("[email]", message)\n'),
    ]),
    "OPS-429": ("Round discounted prices half up (OPS-429)", [
        _append("src/tillroll/discounts.py",
                '"""Discount helpers."""\nfrom __future__ import annotations\n\n\n'
                "def apply_discount(price_minor: int, percent: int) -> int:\n"
                '    """Price after a percentage discount, rounded half up to the nearest penny."""\n'
                "    return (price_minor * (100 - percent) + 50) // 100\n"),
    ]),
}


# --------------------------------------------------------------- set-up code
def _write_manifest(mig_dir: Path) -> None:
    entries = [
        {"id": p.name[:4], "file": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        for p in sorted(mig_dir.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    ]
    (mig_dir / "manifest.json").write_text(json.dumps({"migrations": entries}, indent=2) + "\n")


def _dump_schema(repo: Path) -> None:
    subprocess.run(["python3", "-m", "tillroll.db", "dump-schema"], cwd=repo, check=True,
                   env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin"}, capture_output=True)


def _git(wd: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=Tillroll Dev", "-c", "user.email=dev@tillroll.example", *args],
                   cwd=wd, check=True, capture_output=True)


def prepare(task: Task, workdir: Path, skills_dir: Path | None = None) -> None:
    """Copy the fixture to `workdir`, tag it v1.4.2, replay the task's later
    history as commits (code, migrations, changelog), then install skills."""
    shutil.copytree(FIXTURE, workdir, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    _git(workdir, "init", "-q", "-b", "main")
    _git(workdir, "add", "-A")
    _git(workdir, "commit", "-q", "-m", "Release 1.4.2")
    _git(workdir, "tag", "v1.4.2")
    mig = workdir / "db" / "migrations"
    n = 4
    for slug, ticket, up, down in task.extra_migrations:
        n += 1
        text = (f"-- migration: {n:04d}\n-- ticket: {ticket}\n-- reversible: yes\n"
                f"-- +up\n{up}\n-- +down\n{down}\n")
        (mig / f"{n:04d}_{slug}.sql").write_text(text)
        _write_manifest(mig)
        _dump_schema(workdir)
        _git(workdir, "add", "-A")
        _git(workdir, "commit", "-q", "-m", f"Migration {n:04d}: {slug.replace('_', ' ')} ({ticket})")
    for ticket in task.work:
        msg, edits = CODE_CHANGES[ticket]
        for edit in edits:
            edit(workdir)
        _git(workdir, "add", "-A")
        _git(workdir, "commit", "-q", "-m", msg)
    if task.unreleased:
        cl = workdir / "CHANGELOG.md"
        text = cl.read_text().replace("## [Unreleased]\n", "## [Unreleased]\n\n" + task.unreleased, 1)
        cl.write_text(text)
        _git(workdir, "add", "-A")
        _git(workdir, "commit", "-q", "-m", "Changelog entries for unreleased work")
    if skills_dir is not None:
        shutil.copytree(skills_dir, workdir / ".claude" / "skills")
        _git(workdir, "add", "-A")
        _git(workdir, "commit", "-q", "-m", "Add team skills")
