#!/usr/bin/env python3
"""Extract a SQLite database into structured JSON using a declarative plan.

The plan (JSON) describes the main entity table, the join keys, optional
lookup/enum resolution, and the metadata table that supplies grid dimensions
when ``key_kind == "xy"``. The script preserves every main-table row
(LEFT-JOIN semantics) and applies lookups in place.

Plan shape:
    {
      "main_table":   "Plots",        # required
      "id_column":    "ID",           # default "ID"
      "key_kind":     "xy",           # "id" (default) or "xy"
      "metadata_table": "Map",        # optional single-row config table
      "width_column":  "Width",       # required if key_kind == "xy"
      "height_column": "Height",      # optional
      "container_key": "tiles",       # output key name; default "items"
      "joins": [
        {"table": "PlotFeatures",  "on": "ID", "fields": ["FeatureType"]},
        {"table": "PlotResources", "on": "ID", "fields": ["ResourceType"]}
      ],
      "lookups": [
        {"table": "FeatureTypes", "key": "Type", "value": "Name", "for_field": "FeatureType"}
      ]
    }

Usage:
    python extract_to_json.py <db_path> --plan plan.json [--shape map|array] [--out out.json]

Shape:
    array (default): { "metadata": {...}, "<container_key>": [ {...}, ... ] }
    map:             { "metadata": {...}, "<container_key>": { "x,y": {...}, ... } }
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from typing import Any


def _quote(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


def _coord_key(idx: int, width: int) -> str:
    return f"{idx % width},{idx // width}"


def _fetch_metadata(cursor: sqlite3.Cursor, table: str) -> dict:
    cursor.execute(f"SELECT * FROM {_quote(table)} LIMIT 1")
    row = cursor.fetchone()
    return dict(row) if row else {}


def _load_lookup(cursor: sqlite3.Cursor, spec: dict) -> dict:
    cursor.execute(
        f"SELECT {_quote(spec['key'])}, {_quote(spec['value'])} "
        f"FROM {_quote(spec['table'])}"
    )
    return {row[0]: row[1] for row in cursor.fetchall()}


def extract(db_path: str, plan: dict, shape: str = "array") -> dict[str, Any]:
    if "main_table" not in plan:
        raise ValueError("plan must include 'main_table'")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    metadata: dict[str, Any] = {}
    width: int | None = None
    if plan.get("metadata_table"):
        metadata = _fetch_metadata(cursor, plan["metadata_table"])
        if plan.get("width_column") and plan["width_column"] in metadata:
            width = int(metadata[plan["width_column"]])

    key_kind = plan.get("key_kind", "id")
    id_column = plan.get("id_column", "ID")
    main_table = plan["main_table"]

    if key_kind == "xy" and width is None:
        raise ValueError(
            "key_kind='xy' requires metadata_table + width_column in plan"
        )

    items: dict[Any, dict[str, Any]] = {}
    cursor.execute(f"SELECT * FROM {_quote(main_table)}")
    for row in cursor.fetchall():
        item = dict(row)
        idx = item.get(id_column)
        if key_kind == "xy" and idx is not None:
            idx_int = int(idx)
            item["x"] = idx_int % width  # type: ignore[operator]
            item["y"] = idx_int // width  # type: ignore[operator]
            key: Any = f"{item['x']},{item['y']}"
        else:
            key = idx
        items[key] = item

    for join in plan.get("joins", []):
        try:
            cursor.execute(f"SELECT * FROM {_quote(join['table'])}")
        except sqlite3.OperationalError as exc:
            print(
                f"WARN: join table {join['table']!r} not present: {exc}",
                file=sys.stderr,
            )
            continue
        for row in cursor.fetchall():
            row_dict = dict(row)
            join_key = row_dict.get(join["on"])
            if join_key is None:
                continue
            if key_kind == "xy":
                key = _coord_key(int(join_key), width)  # type: ignore[arg-type]
            else:
                key = join_key
            target = items.get(key)
            if target is None:
                continue
            fields = join.get("fields") or [
                k for k in row_dict if k != join["on"]
            ]
            for field in fields:
                if field in row_dict:
                    target[field] = row_dict[field]

    for spec in plan.get("lookups", []):
        try:
            mapping = _load_lookup(cursor, spec)
        except sqlite3.OperationalError as exc:
            print(
                f"WARN: lookup table {spec.get('table')!r} not present: {exc}",
                file=sys.stderr,
            )
            continue
        target_field = spec["for_field"]
        for item in items.values():
            v = item.get(target_field)
            if v in mapping:
                item[target_field] = mapping[v]

    conn.close()

    container_key = plan.get("container_key", "items")
    if shape == "map":
        out_items: Any = {str(k): v for k, v in items.items()}
    else:
        out_items = list(items.values())
    return {"metadata": metadata, container_key: out_items}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Extract SQLite to structured JSON.")
    p.add_argument("db_path")
    p.add_argument("--plan", required=True, help="Path to JSON extraction plan.")
    p.add_argument(
        "--shape",
        choices=["map", "array"],
        default="array",
        help="Container shape (default array).",
    )
    p.add_argument("--out", help="Write JSON to this file instead of stdout.")
    args = p.parse_args(argv)

    with open(args.plan) as f:
        plan = json.load(f)

    result = extract(args.db_path, plan, shape=args.shape)
    payload = json.dumps(result, indent=2, default=str)
    if args.out:
        with open(args.out, "w") as f:
            f.write(payload)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
