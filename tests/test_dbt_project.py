"""The dbt project and the ingest registry (sources.yml) describe the same datasets."""

import yaml

from ingest.config import ROOT, load_registry

DBT = ROOT / "dbt"


def dbt_sources() -> dict[str, dict]:
    sources = yaml.safe_load((DBT / "models" / "staging" / "_raw__sources.yml").read_text())
    (raw,) = sources["sources"]
    return {t["name"]: t for t in raw["tables"] if "identifier" in t}


def test_every_registered_dataset_is_a_dbt_source():
    registry = {d.id: d for d in load_registry().datasets}
    tables = dbt_sources()
    assert {t["identifier"] for t in tables.values()} == set(registry)
    for name, table in tables.items():
        dataset = registry[table["identifier"]]
        assert name == f"{dataset.era}_{dataset.year}"
        assert table["meta"] == {"dataset_id": dataset.id, "era": dataset.era, "year": dataset.year}


def test_staging_unions_every_dataset_of_its_era():
    project = yaml.safe_load((DBT / "dbt_project.yml").read_text())
    tables = dbt_sources()
    for era in ("legacy", "current"):
        expected = sorted(n for n, t in tables.items() if t["meta"]["era"] == era)
        assert sorted(project["vars"][f"{era}_datasets"]) == expected
