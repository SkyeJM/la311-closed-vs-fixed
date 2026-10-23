"""Pinned dataset schemas: each Socrata view's columns and saved filter as last reviewed.

Pulls compare live metadata with the pin and fail loudly on any drift. The saved filter is part
of the pin because it defines the dataset's population: a silently added request type would
shift every rate. Display names are kept because the bulk CSV export uses them as headers.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ingest.config import SCHEMAS_DIR


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def normalize_filter(query: str | None) -> str:
    return " ".join((query or "").split())


def schema_hash(columns: list[dict]) -> str:
    return _sha("\n".join(f"{c['field']}:{c['type']}" for c in columns))


def pin_from_metadata(meta: dict) -> dict:
    columns = [
        {"field": c["fieldName"], "type": c["dataTypeName"], "display": c["name"]}
        for c in meta["columns"]
    ]
    saved_filter = normalize_filter(meta.get("queryString"))
    return {
        "id": meta["id"],
        "name": meta["name"],
        "parent": meta.get("modifyingViewUid"),
        "schema_hash": schema_hash(columns),
        "filter_hash": _sha(saved_filter),
        "saved_filter": saved_filter,
        "columns": columns,
    }


def diff_pins(pinned: dict, live: dict) -> list[str]:
    """Readable differences between a pinned schema and live metadata; empty means no drift."""
    old = {c["field"]: c for c in pinned["columns"]}
    new = {c["field"]: c for c in live["columns"]}
    problems = [f"column removed: {name}" for name in old.keys() - new.keys()]
    problems += [f"column added: {name} ({new[name]['type']})" for name in new.keys() - old.keys()]
    for name in old.keys() & new.keys():
        if old[name]["type"] != new[name]["type"]:
            problems.append(f"type changed: {name} {old[name]['type']} -> {new[name]['type']}")
        if old[name]["display"] != new[name]["display"]:
            problems.append(
                f"display name changed: {name} {old[name]['display']!r} -> {new[name]['display']!r}"
            )
    if pinned["filter_hash"] != live["filter_hash"]:
        problems.append("saved filter changed: the dataset's population may have changed")
    return sorted(problems)


def pin_path(dataset_id: str, schemas_dir: Path = SCHEMAS_DIR) -> Path:
    return schemas_dir / f"{dataset_id}.json"


def save_pin(pin: dict, schemas_dir: Path = SCHEMAS_DIR) -> Path:
    path = pin_path(pin["id"], schemas_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pin, indent=2, ensure_ascii=False) + "\n")
    return path


def load_pin(dataset_id: str, schemas_dir: Path = SCHEMAS_DIR) -> dict:
    path = pin_path(dataset_id, schemas_dir)
    if not path.exists():
        raise FileNotFoundError(
            f"No pinned schema for {dataset_id}. Review it, then run "
            f"`uv run python -m ingest pin --source {dataset_id}`."
        )
    return json.loads(path.read_text())
