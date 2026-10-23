"""Paths, environment variables, and the pinned dataset registry (sources.yml)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "sources.yml"
SCHEMAS_DIR = ROOT / "ingest" / "schemas"
UNIFIED_FIELDS_FILE = ROOT / "ingest" / "unified_fields.yml"
DATA_DIR = ROOT / "data"
SAMPLES_DIR = DATA_DIR / "samples"
RAW_DIR = DATA_DIR / "raw"

load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Dataset:
    id: str
    name: str
    era: str  # "legacy" or "current": the system of record, never inferred from dates
    year: int
    refresh: str = "static"  # "static", or "incremental" for the live current-year dataset


@dataclass(frozen=True)
class Registry:
    domain: str
    datasets: tuple[Dataset, ...]
    ignored: dict[str, str] = field(default_factory=dict)  # catalog id -> why it isn't a source

    def get(self, dataset_id: str) -> Dataset:
        for dataset in self.datasets:
            if dataset.id == dataset_id:
                return dataset
        raise KeyError(f"{dataset_id} is not registered in sources.yml")


def load_registry(path: Path = SOURCES_FILE) -> Registry:
    raw = yaml.safe_load(path.read_text())
    return Registry(
        domain=raw["domain"],
        datasets=tuple(Dataset(**d) for d in raw["datasets"]),
        ignored={item["id"]: item["reason"] for item in raw.get("ignored", [])},
    )


def socrata_app_token() -> str | None:
    return os.environ.get("SOCRATA_APP_TOKEN") or None
