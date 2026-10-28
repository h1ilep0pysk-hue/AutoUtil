"""Inspect a journal.sqlite database without leaking user paths.

Usage:
    python tools/inspect_db.py <path-to-journal.sqlite>

Prints, for the ``moves`` and ``deferred`` tables:
  - PRAGMA table_info (column names, types, constraints)
  - row count and, for path-bearing columns, only a coarse mask
    (drive count / relative count) — never the paths themselves.
"""

import sqlite3
import sys
from pathlib import Path

TABLES = ("moves", "deferred")
# Columns that may contain user paths; we report masks, not values.
PATH_COLUMNS = ("src", "dst", "path", "trashed")


def _mask(values: list[str | None]) -> str:
    """Coarse summary of path-like values: counts only."""
    total = len(values)
    empty = sum(1 for v in values if not v)
    drive = sum(1 for v in values if v and len(v) >= 2 and v[1] == ":")
    other = total - empty - drive
    return f"total={total} empty={empty} absolute={drive} other={other}"


def inspect(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        existing = {
            row[0]
            for row in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for table in TABLES:
            print(f"== table: {table} ==")
            if table not in existing:
                print("  (absent)")
                continue
            cols = cur.execute(f"PRAGMA table_info({table})").fetchall()
            print("  columns:")
            for cid, name, ctype, notnull, dflt, pk in cols:
                flags = []
                if pk:
                    flags.append("PK")
                if notnull:
                    flags.append("NOT NULL")
                if dflt is not None:
                    flags.append(f"DEFAULT {dflt}")
                suffix = f" [{', '.join(flags)}]" if flags else ""
                print(f"    {name}: {ctype}{suffix}")
            (count,) = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            print(f"  rows: {count}")
            col_names = [c[1] for c in cols]
            for col in PATH_COLUMNS:
                if col in col_names and count:
                    values = [
                        r[0]
                        for r in cur.execute(f"SELECT {col} FROM {table}").fetchall()
                    ]
                    print(f"  {col} mask: {_mask(values)}")
    finally:
        conn.close()


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    db_path = Path(argv[1])
    if not db_path.exists():
        print(f"not found: {db_path.name}")
        return 1
    inspect(db_path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
