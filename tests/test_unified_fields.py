"""The unified-schema crosswalk must agree with every pinned dataset schema."""

import pytest
import yaml

from ingest.config import UNIFIED_FIELDS_FILE, load_registry
from ingest.schema import load_pin

SPEC = yaml.safe_load(UNIFIED_FIELDS_FILE.read_text())
DATASETS = load_registry().datasets


def pinned_fields(dataset_id: str) -> set[str]:
    return {c["field"] for c in load_pin(dataset_id)["columns"]}


@pytest.mark.parametrize("dataset", DATASETS, ids=lambda d: d.id)
def test_every_mapped_field_exists(dataset):
    fields = pinned_fields(dataset.id)
    for unified, mapping in SPEC["fields"].items():
        source = mapping.get(dataset.era)
        if source is None or dataset.id in mapping.get("missing_in", []):
            continue
        assert source in fields, f"{unified} -> {source} is not in {dataset.id}"


@pytest.mark.parametrize("dataset", DATASETS, ids=lambda d: d.id)
def test_every_source_field_is_mapped_or_dropped(dataset):
    mapped = {m[dataset.era] for m in SPEC["fields"].values() if m.get(dataset.era)}
    unaccounted = pinned_fields(dataset.id) - mapped - set(SPEC["dropped"][dataset.era])
    assert not unaccounted, f"{dataset.id} has unmapped fields: {sorted(unaccounted)}"


def test_missing_in_exceptions_are_still_true():
    for unified, mapping in SPEC["fields"].items():
        for dataset_id in mapping.get("missing_in", []):
            source = mapping["legacy"]
            assert source not in pinned_fields(dataset_id), (
                f"{dataset_id} now has {source}; remove it from {unified}.missing_in"
            )
