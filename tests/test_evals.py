"""The eval harness offline: the golden set's shape, expected values and scoring."""

import re

import pytest

from ai.agent import answer, tools
from api import metrics
from evals import expected, score

GOLDEN = expected.load()
QUESTIONS = GOLDEN["questions"]


def test_the_golden_set_has_the_brief_shape():
    assert len(QUESTIONS) >= 40
    assert sum(q["lang"] == "es" for q in QUESTIONS) >= 5
    assert len({q["id"] for q in QUESTIONS}) == len(QUESTIONS)
    kinds = {q["kind"] for q in QUESTIONS}
    assert kinds == {"numeric", "qualify", "decline"}


@pytest.mark.parametrize("q", QUESTIONS, ids=[q["id"] for q in QUESTIONS])
def test_each_question_is_well_formed(q):
    catalog = metrics.catalog().metrics
    assert set(q["evidence"]) <= set(answer.EVIDENCE_LEVELS)
    assert set(q["answer_type"]) <= set(answer.ANSWER_TYPES)
    assert set(q["metrics"]) <= set(catalog)
    assert bool(q.get("expect")) == (q["kind"] == "numeric")
    captured = set()
    for item in q.get("expect", []):
        assert item["unit"] in GOLDEN["tolerance"]
        if "sql" in item:
            continue
        assert item["metric"] in catalog
        dims = set(tools.dimensions())
        assert set(item.get("filters", {})) <= dims and set(item.get("group_by", [])) <= dims
        captured |= set(item.get("capture", {}).values())
    for caveat in q.get("caveats", []):
        assert set(re.findall(r"{(\w+)}", caveat)) <= captured


@pytest.mark.dbt
def test_expected_numbers_come_from_the_metrics(serving_db):
    window = expected.headline_window(serving_db)
    gap, _ = expected.number(
        serving_db,
        {"metric": "closed_fixed_gap_pp", "window": "headline", "column": "value", "unit": "x"},
        window,
    )
    query = metrics.compile_query("closed_fixed_gap_pp", date_range=window)
    assert gap == pytest.approx(metrics.run(serving_db, query)[0]["value"])
    rate, _ = expected.number(
        serving_db,
        {"metric": "closure_rate", "filters": {"era": "current"}, "unit": "percent"},
        window,
    )
    assert 0 <= rate <= 100  # a share comes back as a percent
    count, _ = expected.number(
        serving_db, {"sql": "select count(*) from dim_resolution_code", "unit": "count"}, window
    )
    assert count > 0


TOLERANCE = GOLDEN["tolerance"]


def run_with(reply: dict, problems=(), tool_calls=()) -> dict:
    events = [
        {"type": "tool_call", "id": f"t{i}", "name": name, "input": args}
        for i, (name, args) in enumerate(tool_calls)
    ]
    return {"answer": {"answer": reply, "problems": list(problems)}, "events": events}


def base_reply(**fields) -> dict:
    return {
        "answer_type": "answered",
        "answer_markdown": "",
        "key_numbers": [],
        "evidence_level": "E1",
        "caveats": [],
        "query_ids": [],
        "chart": None,
        "follow_ups": [],
    } | fields


ITEM = {
    "lang": "en",
    "kind": "numeric",
    "metrics": ["verified_fix_rate"],
    "evidence": ["E1"],
    "answer_type": ["answered"],
}
EXPECTED = {"numbers": [{"value": 62.1227, "unit": "percent"}], "context": {}}


def test_numbers_match_in_key_numbers_or_prose():
    key = {"label": "x", "value": 62.1, "unit": "percent", "metric": None, "query_id": "q1"}
    calls = [("query_metric", {"metric": "verified_fix_rate"})]
    result = score.score(
        ITEM, EXPECTED, run_with(base_reply(key_numbers=[key]), tool_calls=calls), None, TOLERANCE
    )
    assert result["passed"] and result["checks"]["governed_metric"]
    prose = run_with(base_reply(answer_markdown="About **62%** were fixed."))
    assert score.score(ITEM, EXPECTED, prose, None, TOLERANCE)["checks"]["numeric"]


def test_wrong_numbers_and_failed_checks_fail():
    wrong = run_with(base_reply(answer_markdown="**58.3%** were fixed.", evidence_level="E2"))
    result = score.score(ITEM, EXPECTED, wrong, None, TOLERANCE)
    assert result["checks"]["numeric"] is False and result["checks"]["evidence"] is False
    assert result["checks"]["governed_metric"] is False and not result["passed"]
    flagged = run_with(base_reply(answer_markdown="**62.1%**"), problems=["bad"])
    assert (
        score.score(ITEM, EXPECTED, flagged, None, TOLERANCE)["checks"]["numbers_supported"]
        is False
    )


def test_the_judge_verdict_feeds_rubric_causal_and_language():
    item = ITEM | {"caveats": ["Says A", "Says B"], "metrics": []}
    verdict = {
        "rubric": [{"item": 1, "met": True, "quote": "a"}, {"item": 2, "met": False, "quote": ""}],
        "causal_claim": True,
    }
    run = run_with(base_reply(answer_markdown="**62.1%** of the requests were fixed."))
    checks = score.score(item, EXPECTED, run, verdict, TOLERANCE)["checks"]
    assert checks["rubric"] is False and checks["no_causal_claim"] is False and checks["language"]


def test_language_is_read_from_the_prose():
    assert score.language("El **62.1%** de las solicitudes se arreglaron en la ciudad.") == "es"
    assert (
        score.language("Of the requests, **62.1%** were fixed in the `closed_rate` data.") == "en"
    )
