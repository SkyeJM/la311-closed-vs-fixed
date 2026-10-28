"""findings.json builds on the synthetic fixtures, and every number points at a recorded query."""

import json

import pytest

from findings import build

pytestmark = pytest.mark.dbt


@pytest.fixture(scope="module")
def result(dbt_build, serving_db):
    tmp = dbt_build[2]
    return build.build(tmp / "serving.duckdb", tmp / "warehouse.duckdb")


def query_ids(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "query_ids":
                yield from value
            else:
                yield from query_ids(value)
    elif isinstance(node, list):
        for item in node:
            yield from query_ids(item)


def test_every_section_is_present(result):
    for section in [
        "data",
        "headline",
        "q1_outcome_mix",
        "q2_where_the_gap_is",
        "q3_bulky_items",
        "q4_cutover",
        "q5_proxy_validation",
        "e2_parameters",
    ]:
        assert section in result, section
    assert result["status"] == "provisional"  # the fixtures run with code_map_final: false


def test_every_cited_query_was_recorded_with_its_sql(result):
    cited = set(query_ids({k: v for k, v in result.items() if k != "queries"}))
    assert cited and cited <= set(result["queries"])
    for query in result["queries"].values():
        assert query["sql"].lower().lstrip().startswith(("select", "with"))
        assert query["database"] in ("serving", "warehouse")


def test_numbers_are_rounded_and_serializable(result):
    text = json.dumps(result, allow_nan=False)
    assert "NaN" not in text
    assert result["data"]["service_requests"]["current"] == 15
    assert result["headline"]["window"]["to_month"] == "2026-03-01"  # 60 days before 2026-06-01
