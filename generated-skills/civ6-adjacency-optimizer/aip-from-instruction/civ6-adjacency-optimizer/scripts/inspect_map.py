#!/usr/bin/env python3
"""Dump structure and sample rows from a .Civ6Map SQLite file.

Usage:
    python inspect_map.py <path/to/map.Civ6Map>

Prints:
    - file magic / first 16 bytes
    - list of tables
    - PRAGMA table_info for each table
    - first 3 rows from each table
    - distinct TerrainType / FeatureType / ResourceType values from Plots

Use this as the first step on any new scenario. Verify column names
before depending on them in parse_map.py.
"""
import sqlite3
import sys
from pathlib import Path


def main(path):
    p = Path(path)
    if not p.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    with p.open("rb") as f:
        header = f.read(16)
    print(f"=== File header (16 bytes) ===")
    print(repr(header))
    if not header.startswith(b"SQLite format 3"):
        print("WARN: file is not a SQLite database; see references/civ6map-format.md")
        sys.exit(2)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row

    print("\n=== Tables ===")
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )]
    for t in tables:
        print(f"  {t}")

    for t in tables:
        print(f"\n=== {t} columns ===")
        for col in conn.execute(f"PRAGMA table_info({t})"):
            print(f"  {col['name']}\t{col['type']}\tnull={col['notnull']}")
        print(f"--- {t} first 3 rows ---")
        rows = conn.execute(f"SELECT * FROM {t} LIMIT 3").fetchall()
        for r in rows:
            print(f"  {dict(r)}")
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"--- {t} total rows: {n}")

    if "Plots" in tables:
        print("\n=== Distinct values in Plots ===")
        for col in ("TerrainType", "FeatureType", "ResourceType"):
            try:
                vals = [r[0] for r in conn.execute(
                    f"SELECT DISTINCT {col} FROM Plots WHERE {col} IS NOT NULL"
                )]
                print(f"  {col}: {sorted(vals)}")
            except sqlite3.OperationalError as e:
                print(f"  {col}: (no such column) {e}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: inspect_map.py <map.Civ6Map>", file=sys.stderr)
        sys.exit(64)
    main(sys.argv[1])
