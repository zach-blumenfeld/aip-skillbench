#!/usr/bin/env python3
"""Deterministic SQLite schema introspection.

Dumps every table in the database with columns, primary key, foreign keys,
indexes (including UNIQUE constraints), row count, and a few sample rows.
The output is JSON intended for an agent to reason about — it replaces the
SQL introspection queries that an agent would otherwise have to issue one
at a time.

Usage:
    python explore_schema.py <db_path> [--samples N] [--out FILE]

Output shape (stdout, pretty-printed JSON):
    {
      "db_path": "...",
      "tables": {
        "<TableName>": {
          "columns":      [{"name", "type", "nullable", "default"}, ...],
          "primary_key":  ["col", ...],
          "foreign_keys": [{"from", "ref_table", "ref_column"}, ...],
          "indexes":      [{"name", "unique", "origin", "columns"}, ...],
          "row_count":    <int|null>,
          "sample_rows":  [{<col>: <value>}, ...]
        },
        ...
      }
    }

Stdlib-only (sqlite3, json, argparse) — no install step.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def _quote(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


def list_tables(cur: sqlite3.Cursor) -> list[str]:
    cur.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    )
    return [r[0] for r in cur.fetchall()]


def table_info(cur: sqlite3.Cursor, table: str) -> tuple[list[dict], list[str]]:
    cur.execute(f"PRAGMA table_info({_quote(table)})")
    cols: list[dict] = []
    pk: list[tuple[int, str]] = []
    for cid, name, ctype, notnull, dflt, pkpos in cur.fetchall():
        cols.append(
            {
                "name": name,
                "type": ctype,
                "nullable": not bool(notnull),
                "default": dflt,
            }
        )
        if pkpos:
            pk.append((pkpos, name))
    pk.sort()
    return cols, [n for _, n in pk]


def foreign_keys(cur: sqlite3.Cursor, table: str) -> list[dict]:
    try:
        cur.execute(f"PRAGMA foreign_key_list({_quote(table)})")
    except sqlite3.Error:
        return []
    out: list[dict] = []
    for row in cur.fetchall():
        # (id, seq, ref_table, from_col, to_col, on_update, on_delete, match)
        out.append(
            {
                "from": row[3],
                "ref_table": row[2],
                "ref_column": row[4],
            }
        )
    return out


def indexes(cur: sqlite3.Cursor, table: str) -> list[dict]:
    try:
        cur.execute(f"PRAGMA index_list({_quote(table)})")
    except sqlite3.Error:
        return []
    out: list[dict] = []
    for row in cur.fetchall():
        # (seq, name, unique, origin, partial) — older SQLite may omit partial.
        name = row[1]
        unique = bool(row[2])
        origin = row[3] if len(row) > 3 else None
        try:
            cur.execute(f"PRAGMA index_info({_quote(name)})")
            cols = [r[2] for r in cur.fetchall()]
        except sqlite3.Error:
            cols = []
        out.append({"name": name, "unique": unique, "origin": origin, "columns": cols})
    return out


def sample_rows(cur: sqlite3.Cursor, table: str, n: int) -> list[dict]:
    try:
        cur.execute(f"SELECT * FROM {_quote(table)} LIMIT ?", (n,))
        return [dict(r) for r in cur.fetchall()]
    except sqlite3.Error:
        return []


def row_count(cur: sqlite3.Cursor, table: str) -> int | None:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {_quote(table)}")
        return cur.fetchone()[0]
    except sqlite3.Error:
        return None


def explore(db_path: Path, n_samples: int = 3) -> dict:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    tables: dict[str, dict] = {}
    for table in list_tables(cur):
        cols, pk = table_info(cur, table)
        tables[table] = {
            "columns": cols,
            "primary_key": pk,
            "foreign_keys": foreign_keys(cur, table),
            "indexes": indexes(cur, table),
            "row_count": row_count(cur, table),
            "sample_rows": sample_rows(cur, table, n_samples),
        }
    conn.close()
    return {"db_path": str(db_path), "tables": tables}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("db_path", type=Path, help="Path to the SQLite database file.")
    p.add_argument(
        "--samples",
        type=int,
        default=3,
        help="Sample rows to pull per table (default 3).",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write JSON to this file instead of stdout.",
    )
    args = p.parse_args(argv)

    if not args.db_path.exists():
        print(f"error: {args.db_path} not found", file=sys.stderr)
        return 1
    data = explore(args.db_path, args.samples)
    text = json.dumps(data, indent=2, default=str)
    if args.out:
        args.out.write_text(text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
