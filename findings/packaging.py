"""The portfolio documents, rendered from the numbers (brief section 9).

    uv run python -m findings.packaging          # make packaging

docs/templates/ holds the prose with {placeholders}. This fills them from findings.json, which
also records the eval results, and from a few settings read from code (the metric count, the
step cap, the rate limit). So README.md, docs/CASE_STUDY.md, docs/DEMO_SCRIPT.md,
docs/RESUME_BULLETS.md and docs/INTERVIEW_PREP.md never type a number by hand.
tests/test_packaging.py re-renders them, fails on drift, and checks that no template types a
number itself.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
FINDINGS = ROOT / "findings" / "findings.json"
TEMPLATES = ROOT / "docs" / "templates"
OUTPUTS = {
    "README.md": ROOT / "README.md",
    "CASE_STUDY.md": ROOT / "docs" / "CASE_STUDY.md",
    "DEMO_SCRIPT.md": ROOT / "docs" / "DEMO_SCRIPT.md",
    "RESUME_BULLETS.md": ROOT / "docs" / "RESUME_BULLETS.md",
    "INTERVIEW_PREP.md": ROOT / "docs" / "INTERVIEW_PREP.md",
}
MODELS = {"claude-haiku-5-5": "haiku", "claude-sonnet-5-5": "sonnet", "claude-opus-5-5": "opus"}


def pct(share: float, digits: int = 0) -> str:
    return f"{share * 100:.{digits}f}%"


def num(value: float) -> str:
    return f"{value:,.0f}"


def month(iso: str) -> str:
    return date.fromisoformat(iso[:10]).strftime("%b %Y")


def day(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return f"{d:%b} {d.day}, {d.year}"


def settings() -> dict[str, float]:
    """The few numbers the documents quote from code rather than from data."""
    from ai.agent.loop import Settings
    from api.guards import Policy

    catalog = yaml.safe_load((ROOT / "metrics.yml").read_text())
    sources = yaml.safe_load((ROOT / "sources.yml").read_text())
    golden = yaml.safe_load((ROOT / "evals" / "golden.yaml").read_text())
    outcomes = (ROOT / "dbt" / "seeds" / "closure_outcomes.csv").read_text().strip().splitlines()
    policy, agent = Policy(), Settings()
    return {
        "classes": len(outcomes) - 1,
        "spanish_questions": sum(q["lang"] == "es" for q in golden["questions"]),
        "metrics": len(catalog["metrics"]),
        "datasets": len(sources["datasets"]),
        "max_steps": agent.max_steps,
        "rate_limit": policy.rate_limit_per_hour,
        "daily_cap": policy.daily_cap_usd,
    }


def context(findings: dict, evals: dict, code: dict) -> dict[str, str]:
    h = findings["headline"]
    q1, q2 = findings["q1_outcome_mix"], findings["q2_where_the_gap_is"]
    q3, q4, q5 = findings["q3_bulky_items"], findings["q4_cutover"], findings["q5_proxy_validation"]
    params, data, labeling = findings["parameters"], findings["data"], findings["ai_labeling"]
    mix = {m["closure_outcome"]: m["share"] for m in q1["mix"]}
    pickups = next(r for r in q3["by_request_type"] if r["request_type"] == "All pickups")
    item_not_out = next(c for c in q2["top_codes"] if c["resolution_code"] == "QC-Item Not Out")
    weekdays = [w["item_not_out_share"] for w in q3["by_closed_weekday"] if w["closed"] >= 10_000]
    follow = q3["new_pickup_request_within_30d"]
    cats = {c["unified_category"]: c for c in q4["categories"]}
    graffiti, lights = cats["Graffiti"], cats["Streetlight repair"]
    bulky = cats["Bulky & dumped item pickups"]
    signs = findings["e2_parameters"]["rereport"]["after_above_before_by_category"].values()
    run = labeling["labeling_run"]
    agree = labeling["ai_human_agreement"]
    fixed_by_speed = q5["instant_close"]["verified_fix_rate"]
    ctx = {
        "data_end": day(data["data_end"]),
        "requests_current": num(data["service_requests"]["current"]),
        "requests_legacy": num(data["service_requests"]["legacy"]),
        "window_from": month(h["window"]["from_month"]),
        "window_to": month(h["window"]["to_month"]),
        "closure_rate": pct(h["closure_rate"], 1),
        "fix_rate": pct(h["verified_fix_rate"], 1),
        "gap": f"{h['gap_pp']:.1f}",
        "base": num(h["fix_rate_base"]),
        "official_closure": pct(h["official_closure_rate"], 1),
        "excluded_neutral": num(h["excluded_from_base"]["neutral"]),
        "excluded_handed_off": num(h["excluded_from_base"]["handed_off"]),
        "mix_work_done": pct(mix["fixed_work_done"]),
        "mix_not_found": pct(mix["not_found"]),
        "mix_unspecified": pct(mix["closed_unspecified"]),
        "mix_handed_off": pct(mix["handed_off"]),
        "unverified_total": num(q2["closed_unverified_total"]),
        "top5_share": pct(q2["top_5_codes_share"]),
        "item_not_out_gap_share": pct(item_not_out["share_of_gap"]),
        "pickups_item_not_out": pct(pickups["item_not_out_share"]),
        "pickups_item_not_out_count": num(pickups["item_not_out"]),
        "nc_count": num(q3["neighborhood_councils"]["compared"]),
        "nc_low": pct(q3["neighborhood_councils"]["lowest"][0]["item_not_out_share"]),
        "nc_high": pct(q3["neighborhood_councils"]["highest"][0]["item_not_out_share"]),
        "weekday_low": pct(min(weekdays)),
        "weekday_high": pct(max(weekdays)),
        "rerequest_item_not_out": pct(follow["QC-Item Not Out"]["rereport_30d_rate"]),
        "rerequest_completed": pct(follow["AR-Request Completed"]["rereport_30d_rate"]),
        "request_before_filing": pct(follow["QC-Item Not Out"]["prior_report_30d_rate"]),
        "graffiti_30d_before": pct(graffiti["closed_within_30d_rate"]["before"]),
        "graffiti_30d_after": pct(graffiti["closed_within_30d_rate"]["after"]),
        "graffiti_cancel_before": pct(graffiti["cancellation_rate"]["before"]),
        "graffiti_cancel_after": pct(graffiti["cancellation_rate"]["after"]),
        "lights_30d_before": pct(lights["closed_within_30d_rate"]["before"]),
        "lights_30d_after": pct(lights["closed_within_30d_rate"]["after"]),
        "pickups_7d_before": pct(bulky["closed_within_7d_rate"]["before"]),
        "pickups_7d_after": pct(bulky["closed_within_7d_rate"]["after"]),
        "instant_fixed": pct(fixed_by_speed["true"]),
        "other_fixed": pct(fixed_by_speed["false"]),
        "rereport_settings": num(sum(s["settings"] for s in signs)),
        "rereport_above": num(sum(s["after_above_before"] for s in signs)),
        "compare_months": num(params["cutover_compare_months"]),
        "followup_days": num(params["headline_followup_days"]),
        "instant_minutes": num(params["instant_close_minutes"]),
        "rereport_radius": num(params["rereport_radius_m"]),
        "rereport_days": num(params["rereport_window_days"]),
        "launch": day(params["cutover_date"]),
        "codes": num(labeling["codes"]),
        "codes_overridden": num(len(agree["overrides"])),
        "agree_codes": pct(agree["share_of_codes"], 1),
        "agree_cases": pct(agree["share_of_service_cases"], 1),
        "label_calls": num(run["calls"]),
        "label_escalated": num(sum(run["escalations"].values())),
        "label_cost": f"${run['cost_usd']:.2f}",
        "metrics": num(code["metrics"]),
        "datasets": num(code["datasets"]),
        "max_steps": num(code["max_steps"]),
        "rate_limit": num(code["rate_limit"]),
        "daily_cap": f"${code['daily_cap']:.2f}",
    }
    rows = {MODELS[m["model"]]: m for m in evals["models"] if m["model"] in MODELS}
    ctx["eval_questions"] = num(rows["sonnet"]["questions"])
    ctx["eval_spanish"] = num(code["spanish_questions"])
    cost = {name: m["cost_per_question_usd"] for name, m in rows.items()}
    ctx["opus_cost_ratio"] = f"{cost['opus'] / cost['sonnet']:.1f}"
    ctx["haiku_cost_ratio"] = f"{cost['sonnet'] / cost['haiku']:.0f}"
    before = evals.get("sonnet_round2")
    if before:
        ctx["sonnet_round2_cost"] = f"${before['cost_usd']['per_question']:.4f}"
        ctx["sonnet_round2_p50"] = f"{before['latency_s']['p50']:.1f}"
        ctx["sonnet_round2_steps"] = f"{before['steps_mean']:.1f}"
        drop = 1 - cost["sonnet"] / before["cost_usd"]["per_question"]
        ctx["sonnet_cost_drop"] = pct(drop)
    ctx["sonnet_steps"] = f"{rows['sonnet'].get('steps_mean', 0):.1f}"
    ctx["classes"] = num(code["classes"])
    for name, m in rows.items():
        ctx[f"{name}_numeric"] = pct(m["numeric_accuracy"])
        ctx[f"{name}_pass"] = pct(m["pass_rate"])
        ctx[f"{name}_cost"] = f"${m['cost_per_question_usd']:.4f}"
        ctx[f"{name}_p50"] = f"{m['latency_s']['p50']:.1f}"
        ctx[f"{name}_p90"] = f"{m['latency_s']['p90']:.1f}"
    return ctx


def load() -> tuple[dict, dict, dict]:
    """findings.json (which also records the eval results) and the settings read from code."""
    findings = json.loads(FINDINGS.read_text())
    evals = dict(findings["ask_evals"]["current"])
    evals["sonnet_round2"] = findings["ask_evals"].get("sonnet_before_step_counter")
    return findings, evals, settings()


def render() -> dict[str, str]:
    ctx = context(*load())
    return {name: (TEMPLATES / name).read_text().format_map(ctx) for name in OUTPUTS}


def main() -> None:
    for name, text in render().items():
        OUTPUTS[name].write_text(text)
        print(f"wrote {OUTPUTS[name].relative_to(ROOT)}")


if __name__ == "__main__":
    main()
