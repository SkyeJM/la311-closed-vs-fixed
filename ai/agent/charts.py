"""make_chart: a Vega-Lite spec bound to one query's rows, validated before the UI sees it.

The model writes the encoding; it never writes the data. The spec names a query_id from the
same answer, and the rows that query returned are injected here, so a chart can only show
numbers a tool produced. Specs that bring their own data, load URLs or link out are rejected;
fields must exist in the query's columns (or be made by the spec's own transforms); the result
must validate against the Vega-Lite 6.5 JSON schema (vendored, gzipped: react-vega 8 renders
Vega-Lite 6).
"""

from __future__ import annotations

import copy
import functools
import gzip
import json
from pathlib import Path

import jsonschema

SCHEMA_FILE = Path(__file__).with_name("vega-lite-6.5.0.schema.json.gz")
SCHEMA_URL = "https://vega.github.io/schema/vega-lite/v6.json"
MAX_ROWS = 500
BANNED_KEYS = {"data", "datasets", "url", "href", "usermeta"}


class ChartRejected(ValueError):
    """The spec breaks a rule; the message says which."""


@functools.cache
def _validator() -> jsonschema.Draft7Validator:
    return jsonschema.Draft7Validator(json.loads(gzip.decompress(SCHEMA_FILE.read_bytes())))


def _walk(node, path=()):
    if isinstance(node, dict):
        for key, value in node.items():
            yield path + (key,), key, value
            yield from _walk(value, path + (key,))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _walk(value, path + (i,))


def _made_fields(spec: dict) -> set[str]:
    """Field names the spec's transforms create (calculate, aggregate, fold ... `as`)."""
    made = set()
    for _, key, value in _walk(spec):
        if key == "as":
            made.update([value] if isinstance(value, str) else value)
    return {m for m in made if isinstance(m, str)}


def build(spec: dict, columns: list[str], rows: list[dict]) -> dict:
    """The renderable spec: the model's spec plus the query's rows. Raises ChartRejected."""
    if not isinstance(spec, dict) or not spec:
        raise ChartRejected("spec must be a Vega-Lite object")
    for path, key, _ in _walk(spec):
        if key in BANNED_KEYS:
            raise ChartRejected(
                f"remove '{'.'.join(map(str, path))}': charts get their data from the query "
                "named by query_id and can't load URLs or link out"
            )
    known = set(columns) | _made_fields(spec)
    for _, key, value in _walk(spec):
        if key == "field" and isinstance(value, str) and value.split(".")[0] not in known:
            raise ChartRejected(
                f"field '{value}' isn't a column of this query ({', '.join(columns)})"
            )
    if len(rows) > MAX_ROWS:
        raise ChartRejected(f"a chart takes at most {MAX_ROWS} rows; aggregate the query first")

    full = copy.deepcopy(spec)
    full["$schema"] = SCHEMA_URL
    full["data"] = {"values": rows}
    error = jsonschema.exceptions.best_match(_validator().iter_errors(full))
    if error is not None:
        where = "/".join(map(str, error.absolute_path)) or "top level"
        raise ChartRejected(f"not a valid Vega-Lite spec at {where}: {error.message[:300]}")
    return full
