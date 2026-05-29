#!/usr/bin/env python3
"""Quick diagnostic queries against a SQLite table.

Emits a JSON report on stdout:
    {
      "table": "...",
      "row_count": int,
      "sample": [ {...}, ... ],
      # when --column is set:
      "null_count_<col>": int,
      "distinct_<col>":   [ ... ]   # capped at --max-distinct entries
    }

Usage:
    python sample_table.py <db_path> <table> [--limit N] [--column COL] [--max-distinct N]

Use to spot-check an extracted JSON against the source DB:
- compare ``row_count`` to ``len(items)`` in the extracted output;
- inspect ``distinct_<col>`` for lookup-resolution sanity;
- compare a few ``sample`` rows against the matching extracted items.
"""
from __future__ import annotations

import argparse
import json
import sqlite3


def _quote(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


def diagnose(
    db_path: str,
    table: str,
    limit: int = 5,
    column: str | None = None,
    max_distinct: int = 50,
) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    out: dict = {"table": table}

    cursor.execute(f"SELECT COUNT(*) AS c FROM {_quote(table)}")
    out["row_count"] = cursor.fetchone()["c"]

    cursor.execute(f"SELECT * FROM {_quote(table)} LIMIT ?", (limit,))
    out["sample"] = [dict(r) for r in cursor.fetchall()]

    if column:
        cursor.execute(
            f"SELECT COUNT(*) AS c FROM {_quote(table)} "
            f"WHERE {_quote(column)} IS NULL"
        )
        out[f"null_count_{column}"] = cursor.fetchone()["c"]

        cursor.execute(
            f"SELECT DISTINCT {_quote(column)} FROM {_quote(table)} "
            f"ORDER BY 1 LIMIT ?",
            (max_distinct,),
        )
        out[f"distinct_{column}"] = [r[0] for r in cursor.fetchall()]

    conn.close()
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Diagnostic queries on a SQLite table.")
    p.add_argument("db_path")
    p.add_argument("table")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument(
        "--column",
        help="If set, also count NULLs and list distinct values for this column.",
    )
    p.add_argument(
        "--max-distinct",
        type=int,
        default=50,
        help="Cap on distinct values returned (default 50).",
    )
    args = p.parse_args(argv)

    report = diagnose(
        args.db_path,
        args.table,
        limit=args.limit,
        column=args.column,
        max_distinct=args.max_distinct,
    )
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
