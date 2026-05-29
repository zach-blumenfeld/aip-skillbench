#!/usr/bin/env python3
"""Introspect a SQLite database and emit a comprehensive schema report as JSON.

For every user table (excluding ``sqlite_*``) the report includes:
- ``columns``: name, declared type, NOT NULL flag, default, primary-key index.
- ``primary_key``: ordered list of PK column names.
- ``indexes``: name, unique flag, columns. Covers UNIQUE constraints.
- ``foreign_keys``: from-column, target table, target column.
- ``row_count``.
- ``sample_rows``: up to ``--sample`` rows (default 3), as dicts.

Usage:
    python explore_schema.py <db_path> [--sample N] [--out file.json]

Exit code 0 on success; 1 on hard errors (e.g., file missing).
PRAGMA failures on individual tables emit a stderr warning but do not abort —
this preserves usefulness against partial / unusual databases.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from typing import Any


def _quote(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


def _safe_fetchall(cursor: sqlite3.Cursor, query: str, params: tuple = ()) -> list:
    try:
        cursor.execute(query, params)
        return cursor.fetchall()
    except sqlite3.OperationalError as exc:
        print(f"WARN: query failed [{query!r}]: {exc}", file=sys.stderr)
        return []


def explore(db_path: str, sample: int = 3) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    tables: list[dict[str, Any]] = []
    cursor.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    for tr in cursor.fetchall():
        name = tr["name"]
        if name.startswith("sqlite_"):
            continue

        columns: list[dict[str, Any]] = []
        pk_pairs: list[tuple[int, str]] = []
        for r in _safe_fetchall(cursor, f"PRAGMA table_info({_quote(name)})"):
            columns.append({
                "name": r["name"],
                "type": r["type"],
                "notnull": bool(r["notnull"]),
                "default": r["dflt_value"],
                "pk": int(r["pk"]),
            })
            if r["pk"]:
                pk_pairs.append((int(r["pk"]), r["name"]))
        primary_key = [n for _, n in sorted(pk_pairs)]

        indexes: list[dict[str, Any]] = []
        for r in _safe_fetchall(cursor, f"PRAGMA index_list({_quote(name)})"):
            cols = [
                ir["name"]
                for ir in _safe_fetchall(
                    cursor, f"PRAGMA index_info({_quote(r['name'])})"
                )
            ]
            indexes.append({
                "name": r["name"],
                "unique": bool(r["unique"]),
                "columns": cols,
            })

        foreign_keys = [
            {"from": r["from"], "to_table": r["table"], "to": r["to"]}
            for r in _safe_fetchall(
                cursor, f"PRAGMA foreign_key_list({_quote(name)})"
            )
        ]

        row_count = 0
        cnt = _safe_fetchall(cursor, f"SELECT COUNT(*) AS c FROM {_quote(name)}")
        if cnt:
            row_count = cnt[0]["c"]

        sample_rows = [
            dict(r)
            for r in _safe_fetchall(
                cursor, f"SELECT * FROM {_quote(name)} LIMIT ?", (sample,)
            )
        ]

        tables.append({
            "name": name,
            "create_sql": tr["sql"],
            "columns": columns,
            "primary_key": primary_key,
            "indexes": indexes,
            "foreign_keys": foreign_keys,
            "row_count": row_count,
            "sample_rows": sample_rows,
        })

    conn.close()
    return {"db_path": db_path, "tables": tables}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Introspect a SQLite DB schema.")
    p.add_argument("db_path", help="Path to SQLite database file.")
    p.add_argument(
        "--sample",
        type=int,
        default=3,
        help="Rows per table to include in sample_rows (default 3).",
    )
    p.add_argument("--out", help="Write JSON to this file instead of stdout.")
    args = p.parse_args(argv)

    report = explore(args.db_path, sample=args.sample)
    payload = json.dumps(report, indent=2, default=str)
    if args.out:
        with open(args.out, "w") as f:
            f.write(payload)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
