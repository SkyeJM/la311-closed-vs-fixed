"""The Ask agent offline: the SQL guard, the locked connection, the number check, charts, the
answer contract, the tools on the fixture serving file, and the loop with a scripted client.
"""

import pytest

from ai.agent import answer, charts, numbers, prompt, sqlguard, tools
from ai.agent.loop import Agent, Budget, Settings, collect
from api import db
from tests.agent_fakes import FakeClient, final, gap_answer, metric_call, reply, tool_turn

ALLOWED = set(tools.SQL_TABLES)


# --- the SQL guard ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "select era, sum(n_requests) from mart_outcomes_monthly group by 1",
        "with t as (select * from dim_resolution_code) select count(*) from t",
        "from main.mart_outcomes_monthly select era limit 2",
        "select * from mart_cutover_periods union all select * from mart_cutover_periods",
    ],
)
def test_the_guard_passes_plain_selects(sql):
    assert sqlguard.check(sql, ALLOWED)


@pytest.mark.parametrize(
    ("sql", "why"),
    [
        ("select * from fct_current_requests", "isn't available"),
        ("select (select count(*) from fct_current_requests)", "isn't available"),
        ("select * from read_csv('/etc/hosts')", "table functions"),
        ("select * from query('select * from fct_current_requests')", "table functions"),
        ("select * from 'data/raw/x.parquet'", "isn't available"),
        ("select * from information_schema.tables", "bare table name"),
        ("select * from other.main.mart_outcomes_monthly", "bare table name"),
        ("select 1; select 2", "exactly one"),
        ("drop table mart_outcomes_monthly", "only SELECT"),
        ("pragma database_list", "only SELECT"),
        ("copy (select 1) to 'x.csv'", "only SELECT"),
        ("attach 'x.duckdb'", "only SELECT"),
        ("select from where", "parse"),
        ("select 1 " + "x" * 5000, "characters"),
    ],
)
def test_the_guard_rejects_everything_else(sql, why):
    with pytest.raises(sqlguard.SqlRejected, match=why):
        sqlguard.check(sql, ALLOWED)


# --- the locked connection -------------------------------------------------------------------


@pytest.mark.dbt
@pytest.mark.parametrize(
    "statement",
    [
        "select * from read_csv('/etc/hosts')",
        "create table x as select 1",
        "set enable_external_access = true",
        "set memory_limit = '64GB'",
        "copy (select 1) to 'leak.csv'",
    ],
)
def test_the_connection_is_locked_even_without_the_guard(agent_db, statement):
    with pytest.raises(Exception):  # noqa: B017 (DuckDB raises several error types here)
        agent_db.cursor().execute(statement)


@pytest.mark.dbt
def test_slow_queries_are_stopped(agent_db):
    with pytest.raises(db.QueryTimeout):
        db.execute(agent_db.cursor(), "select count(*) from range(10000000000)", timeout_s=0.2)


# --- numbers ---------------------------------------------------------------------------------


def test_numbers_are_read_at_the_precision_written():
    found = {
        n.text: n for n in numbers.extract("**62.1%** of 2,064,328; 2.1 million; 62,1 %; 50 m")
    }
    assert found["50"].multiplier == 1.0  # "50 m" is metres, not millions
    assert found["62.1%"].decimals == 1 and found["62.1%"].percent
    assert found["2,064,328"].value == 2064328
    assert found["2.1 million"].multiplier == 1e6
    assert found["62,1 %"].value == 62.1


def test_only_tool_numbers_are_supported():
    pool = numbers.pool([{"value": 0.62123, "n": 2064328, "gap": 25.7207, "hours": 52.3}])
    text = (
        "62.1% of 2,064,328 requests; a 25.7-point gap; about 2.2 days; top 5 in 2025; "
        "`closed_within_7d_rate` on 2025-03-01. But 33.3% and 1,234 are invented."
    )
    assert numbers.unsupported(text, pool) == ["33.3%", "1,234"]


def test_key_numbers_respect_their_unit():
    values = [0.62123, 0.003, 52.3]
    assert numbers.supports(62.1, "percent", values)
    assert numbers.supports(0.3, "percent", values)  # a real 0.3%
    assert not numbers.supports(0.621, "percent", values)  # a share written as a percent
    assert numbers.supports(2.2, "days", values)
    assert not numbers.supports(62.1, "count", values)


# --- charts ----------------------------------------------------------------------------------


ROWS = [{"period": "before", "value_pct": 74.4}, {"period": "after", "value_pct": 65.1}]
SPEC = {
    "mark": "bar",
    "encoding": {
        "x": {"field": "period", "type": "nominal"},
        "y": {"field": "value_pct", "type": "quantitative"},
    },
}


def test_a_chart_gets_the_query_rows_and_validates():
    full = charts.build(SPEC, ["period", "value_pct"], ROWS)
    assert full["data"] == {"values": ROWS}
    assert full["$schema"].endswith("v6.json")


@pytest.mark.parametrize(
    ("change", "why"),
    [
        ({"data": {"values": [{"x": 1}]}}, "remove 'data'"),
        (
            {"encoding": {"x": {"field": "period", "type": "nominal"}, "href": {"field": "x"}}},
            "href",
        ),
        ({"encoding": {"x": {"field": "secret", "type": "nominal"}}}, "isn't a column"),
        ({"mark": "pie-chart"}, "not a valid Vega-Lite spec"),
    ],
)
def test_bad_charts_are_rejected(change, why):
    with pytest.raises(charts.ChartRejected, match=why):
        charts.build(SPEC | change, ["period", "value_pct"], ROWS)


# --- the answer contract -------------------------------------------------------------------


QUERIES = {"q1": {"values": [0.62123, 62.12, 2064328.0]}}
POOL = [0.62123, 62.12, 2064328.0]


def test_a_supported_answer_has_no_problems():
    assert answer.problems(reply(), QUERIES, {}, POOL) == []


def test_answer_problems_name_what_to_fix():
    bad = reply(
        answer_markdown="**62.1%** fixed, and 48.0% of the rest.",
        key_numbers=[
            {"label": "x", "value": 70.0, "unit": "percent", "metric": None, "query_id": "q1"},
            {"label": "y", "value": 1.0, "unit": "count", "metric": None, "query_id": "q9"},
        ],
        chart="c3",
    )
    found = " | ".join(answer.problems(bad, QUERIES, {}, POOL))
    assert "q9" in found and "'x' = 70.0" in found and "c3" in found and "48.0%" in found
    declined = reply(answer_type="declined")
    assert "declined" in " ".join(answer.problems(declined, QUERIES, {}, POOL))


# --- tools on the fixture serving file -----------------------------------------------------


@pytest.mark.dbt
def test_query_metric_records_its_sql_and_annotates_rates(agent_db):
    box = tools.ToolBox(agent_db)
    payload, error = box.run("query_metric", metric_call("closed_fixed_gap_pp"))
    assert not error, payload
    row = payload["rows"][0]
    assert {"a_rate_pct", "b_rate_pct", "value"} <= set(row)
    record = box.queries[payload["query_id"]]
    assert record.sql.startswith("with grouped") and record.metric == "closed_fixed_gap_pp"
    payload, error = box.run(
        "query_metric",
        metric_call("verified_fix_rate", filters=[("is_crew_self_report", ["false"])]),
    )
    assert not error and "value_pct" in payload["rows"][0]


@pytest.mark.dbt
def test_query_metric_suggests_real_filter_values(agent_db):
    box = tools.ToolBox(agent_db)
    payload, error = box.run(
        "query_metric", metric_call("closure_rate", filters=[("unified_category", ["graffiti"])])
    )
    assert error and "closest: Graffiti" in payload["error"]
    payload, error = box.run(
        "query_metric", metric_call("closure_rate", filters=[("cd", ["seven"])])
    )
    assert error and "integer" in payload["error"]


@pytest.mark.dbt
def test_run_sql_reads_aggregates_only(agent_db):
    box = tools.ToolBox(agent_db)
    payload, error = box.run(
        "run_sql", {"sql": "select era, sum(n_requests) as n from mart_outcomes_monthly group by 1"}
    )
    assert not error and payload["query_id"] == "q1"
    payload, error = box.run("run_sql", {"sql": "select * from fct_current_requests"})
    assert error and "query_metric" in payload["error"]


@pytest.mark.dbt
def test_describe_explain_and_chart(agent_db):
    box = tools.ToolBox(agent_db)
    described, error = box.run("describe_table", {"table": "mart_cutover_periods"})
    assert not error and any(c["name"] == "period" for c in described["columns"])
    code, error = box.run("explain_resolution_code", {"code": "duplicate"})
    assert not error and code["codes"][0]["closure_outcome"]
    gap, _ = box.run("query_metric", metric_call("closure_rate", group_by=["unified_category"]))
    spec = {
        "mark": "bar",
        "encoding": {
            "x": {"field": "unified_category", "type": "nominal"},
            "y": {"field": "value_pct", "type": "quantitative"},
        },
    }
    chart, error = box.run("make_chart", {"query_id": gap["query_id"], "spec": spec})
    assert not error and chart["chart_id"] == "c1"
    assert box.charts["c1"]["spec"]["data"]["values"]


@pytest.mark.dbt
def test_the_prompt_holds_definitions_not_data(agent_db):
    text = prompt.build(agent_db, max_steps=8)
    assert "$" not in text.replace("$data", "")
    assert prompt.RULES_HEADING in text
    definitions = text.split(prompt.RULES_HEADING)[0]
    big = [n for n in numbers.pool(definitions) if n > 100 and n != 311 and not 1990 <= n <= 2035]
    assert big == []  # no counts from the data: the model can only quote tools


# --- the loop, with a scripted client --------------------------------------------------------


@pytest.mark.dbt
def test_the_loop_runs_tools_then_answers(agent_db):
    client = FakeClient(
        [tool_turn(("query_metric", metric_call("closed_fixed_gap_pp"))), final(gap_answer())]
    )
    result = collect(Agent(client, agent_db, Settings(model="claude-haiku-5-5")).run("Gap?"))
    kinds = [e["type"] for e in result["events"]]
    assert kinds == [
        "start",
        "model_call",
        "tool_call",
        "tool_result",
        "model_call",
        "answer",
        "done",
    ]
    assert result["answer"]["queries"]["q1"]["sql"]
    assert result["done"]["outcome"] == "answered"
    first = client.calls[0]
    assert first["tool_choice"] == {"type": "auto"}
    assert first["output_config"]["format"]["type"] == "json_schema"
    assert first["system"][0]["cache_control"] == {"type": "ephemeral"}


@pytest.mark.dbt
def test_an_invented_number_goes_back_once(agent_db):
    client = FakeClient(
        [
            tool_turn(("query_metric", metric_call("closed_fixed_gap_pp"))),
            final(gap_answer("The gap is 41.3 points.")),
            final(gap_answer("The gap is 41.3 points.")),
        ]
    )
    result = collect(Agent(client, agent_db, Settings(model="claude-haiku-5-5")).run("Gap?"))
    revision = next(e for e in result["events"] if e["type"] == "revision")
    assert "41.3" in revision["problems"][0]
    assert "41.3" in client.calls[2]["messages"][-1]["content"]
    assert result["answer"]["problems"]  # still wrong after one retry: delivered, flagged
    assert result["done"]["outcome"] == "answered_with_problems"


@pytest.mark.dbt
def test_the_last_step_turns_tools_off(agent_db):
    turns = [tool_turn(("list_metrics", {})) for _ in range(2)] + [final(gap_answer())]
    client = FakeClient(turns)
    settings = Settings(model="claude-haiku-5-5", max_steps=3)
    result = collect(Agent(client, agent_db, settings).run("Anything?"))
    assert [c["tool_choice"]["type"] for c in client.calls] == ["auto", "auto", "none"]
    assert "Step limit" in client.calls[2]["messages"][-1]["content"][-1]["text"]
    assert result["answer"] is not None


@pytest.mark.dbt
def test_the_budget_stops_the_loop(agent_db):
    client = FakeClient([tool_turn(("list_metrics", {}))] * 3)
    budget = Budget(limit_usd=0.0)
    result = collect(Agent(client, agent_db, Settings(model="claude-haiku-5-5"), budget).run("Q"))
    assert result["error"]["code"] == "budget" and not client.calls
