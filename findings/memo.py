"""findings/MEMO.md: the one-page findings memo, rendered from findings.json.

Every number below is read from the findings dict; the prose around it is fixed text. Rerun
`make findings` after the data or the code map changes and the memo follows.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "findings" / "MEMO.md"


def pct(value, digits: int = 0) -> str:
    return "n/a" if value is None else f"{value * 100:.{digits}f}%"


def pp(value, digits: int = 1) -> str:
    return "n/a" if value is None else f"{value:+.{digits}f} pts"


def num(value) -> str:
    return "n/a" if value is None else f"{value:,}"


def month(value: str) -> str:
    from datetime import date

    return date.fromisoformat(value[:10]).strftime("%b %Y")


def _category(q4: dict, name: str) -> dict:
    return next((c for c in q4["categories"] if c["unified_category"] == name), {})


def _before_after(row: dict, metric: str, digits: int = 0) -> str:
    values = row.get(metric, {})
    return f"{pct(values.get('before'), digits)} to {pct(values.get('after'), digits)}"


def render(f: dict) -> str:
    h, q1, q2, q3 = (
        f["headline"],
        f["q1_outcome_mix"],
        f["q2_where_the_gap_is"],
        f["q3_bulky_items"],
    )
    q4, q5 = f["q4_cutover"], f["q5_proxy_validation"]
    mix = {m["closure_outcome"]: m["share"] for m in q1["mix"]}
    categories = q1["by_category"]
    pickups = next((c for c in categories if c["unified_category"].startswith("Bulky")), {})
    base_total = h["fix_rate_base"] or 0
    top_codes = q2["top_codes"]
    item_not_out = next((c for c in top_codes if c["resolution_code"] == "QC-Item Not Out"), {})
    all_pickups = next((r for r in q3["by_request_type"] if r["request_type"] == "All pickups"), {})
    ncs = q3["neighborhood_councils"]
    weekdays = [w["item_not_out_share"] for w in q3["by_closed_weekday"] if w["closed"] >= 10_000]
    followups = q3["new_pickup_request_within_30d"]
    graffiti, lights = _category(q4, "Graffiti"), _category(q4, "Streetlight repair")
    bulky, animals = _category(q4, "Bulky & dumped item pickups"), _category(q4, "Dead animal")
    fix_by_speed = q5["instant_close"]["verified_fix_rate"]
    rereports = q5["rereports_by_outcome"]
    signs = f.get("e2_parameters", {}).get("rereport", {}).get("after_above_before_by_category", {})
    settings = sum(s["settings"] for s in signs.values())
    above = sum(s["after_above_before"] for s in signs.values())
    by_count = q2["largest_gap_count"][0] if q2["largest_gap_count"] else None
    by_rate = q2["largest_gap_rate"][0] if q2["largest_gap_rate"] else None
    instant = [
        v
        for c in q4["categories"]
        for v in c.get("instant_close_rate", {}).values()
        if isinstance(v, float | int) and v is not None
    ]
    qc_follow = followups.get("QC-Item Not Out", {})
    done_follow = followups.get("AR-Request Completed", {})
    follow_place = (
        qc_follow.get("rereport_30d_rate") is not None
        and done_follow.get("rereport_30d_rate") is not None
        and max(qc_follow["rereport_30d_rate"], done_follow["rereport_30d_rate"])
        < qc_follow["prior_report_30d_rate"]
        and abs(qc_follow["rereport_30d_rate"] - done_follow["rereport_30d_rate"]) < 0.05
    )

    # The largest categories with enough fixed and not-fixed closes to compare.
    compared = sorted(
        (
            (groups["fixed"]["eligible"] + groups["not_fixed"]["eligible"], category, groups)
            for category, groups in rereports.items()
            if "fixed" in groups and "not_fixed" in groups
        ),
        key=lambda item: -item[0],
    )[:3]
    rerep_gaps = ", ".join(
        f"{category.lower()} "
        f"{pp((g['not_fixed']['rereport_30d_rate'] - g['fixed']['rereport_30d_rate']) * 100)}"
        for _, category, g in compared
    )

    provisional = f["status"] != "final"
    lines = [
        "# Closed ≠ Fixed: findings memo (v1)",
        "",
        f"Data through {f['data']['data_end'][:10]}. Generated from `findings/findings.json` "
        f"(commit {f.get('git_commit') or 'n/a'}); every number below is in that file with the "
        "query that produced it. Descriptive only: no claim here says why a number is what it is.",
        "",
    ]
    if provisional:
        lines += [
            f"> **Provisional.** {f['status_note']} "
            f"{num(f['data']['code_map']['unmapped_code_service_cases'])} service requests carry "
            "one of those codes, so category-level fix rates below are not yet meaningful where "
            "they dominate (streetlights, scooters, street services).",
            "",
        ]
    lines += [
        "## Headline",
        "",
        f"In the new MyLA311 system (requests filed {month(h['window']['from_month'])} to "
        f"{month(h['window']['to_month'])}, each followed at least "
        f"{f['parameters']['headline_followup_days']} days), **{pct(h['closure_rate'], 1)} of "
        f"requests were marked closed, but only {pct(h['verified_fix_rate'], 1)} carry a "
        f"resolution code saying the work was done: a {h['gap_pp']:.1f}-point gap.** The base "
        f"({num(h['fix_rate_base'])} requests) leaves out "
        f"{num(h['excluded_from_base'].get('neutral'))} duplicates and information-only closes "
        f"and {num(h['excluded_from_base'].get('handed_off'))} intake handoffs, whose own record "
        "can't show a fix. The City's closure rate over every service request in those months is "
        f"{pct(h['official_closure_rate'], 1)}.",
        "",
        "## What the data shows",
        "",
        f"1. **Outcome mix (Q1).** Of requests that ended: work done "
        f"{pct(mix.get('fixed_work_done'))}, not found {pct(mix.get('not_found'))}, closed "
        f"without saying how {pct(mix.get('closed_unspecified'))}, handed off at intake "
        f"{pct(mix.get('handed_off'))}, duplicate {pct(mix.get('duplicate'))}, cancelled "
        f"{pct(mix.get('cancelled'))}"
        + (f", code not mapped yet {pct(mix.get(None))}" if provisional and mix.get(None) else "")
        + ". Bulky and dumped item pickups are "
        f"{pct((pickups.get('fix_rate_base') or 0) / base_total if base_total else None)} of "
        f"the base, so they set the overall rates (pickup gap: {pickups.get('gap_pp', 0):.1f} "
        "points).",
        f"2. **Where the gap is (Q2).** The gap is concentrated in a few codes: five codes "
        f"carry {pct(q2['top_5_codes_share'])} of the {num(q2['closed_unverified_total'])} "
        f'closed-but-unverified requests, and "QC-Item Not Out" alone carries '
        f"{pct(item_not_out.get('share_of_gap'))}. "
        + (
            f"The largest count is {by_count['unified_category']} in council district "
            f"{by_count['cd']} ({num(by_count['closed_unverified'])}); the highest rate among "
            f"groups of {num(q2['min_base'])}+ is {by_rate['unified_category']} "
            f"({by_rate['department']}) in district {by_rate['cd']}, "
            f"{by_rate['gap_pp']:.1f} points."
            if by_count and by_rate
            else ""
        ),
        f'3. **Bulky items (Q3).** "Item not out" closed '
        f"{pct(all_pickups.get('item_not_out_share'))} of pickups "
        f"({num(all_pickups.get('item_not_out'))}). Across {ncs['compared']} neighborhood "
        f"councils with {num(ncs['min_closed'])}+ closed pickups it ranged from "
        f"{pct(ncs['lowest'][0]['item_not_out_share'] if ncs['lowest'] else None)} to "
        f"{pct(ncs['highest'][0]['item_not_out_share'] if ncs['highest'] else None)}; across "
        f"weekdays only from {pct(min(weekdays) if weekdays else None)} to "
        f"{pct(max(weekdays) if weekdays else None)}. A new pickup request within 50 m and 30 "
        f"days followed {pct(qc_follow.get('rereport_30d_rate'))} of item-not-out closes and "
        f"{pct(done_follow.get('rereport_30d_rate'))} of completed pickups, against "
        f"{pct(qc_follow.get('prior_report_30d_rate'))} in the 30 days before an item-not-out "
        "request was filed"
        + (": repeat requests follow the place more than the outcome." if follow_place else "."),
        f"4. **The cutover (Q4).** Comparing the year before the relaunch with the year after "
        f"the overlap (crosswalked categories, crew self-reports out): graffiti closed within 30 "
        f"days went from {_before_after(graffiti, 'closed_within_30d_rate')} and cancellations "
        f"from {_before_after(graffiti, 'cancellation_rate')}; streetlights closed within 30 days "
        f"went from {_before_after(lights, 'closed_within_30d_rate')}; pickups closed within 7 "
        f"days from {_before_after(bulky, 'closed_within_7d_rate')}; dead animals closed within "
        f"7 days from {_before_after(animals, 'closed_within_7d_rate')}. Instant closes were at "
        f"most {pct(max(instant) if instant else None, 1)} of closes in any category and "
        "period.",
        f"5. **Proxy validation (Q5).** Among resident-reported closes in the new system, those "
        f"closed within a minute were verifiably fixed {pct(fix_by_speed.get('true'))} of the "
        f"time, against {pct(fix_by_speed.get('false'))} for the rest. Re-report rates after "
        f"not-fixed closes, minus those after fixed ones: {rerep_gaps or 'n/a'}. Yet the "
        "after-close rate exceeded the "
        f"before-filing baseline in only {above} of {settings} category, era and parameter "
        "settings"
        + (
            ". The proxies carry some signal within a category; they can't stand in for legacy "
            "fix rates."
            if settings and above / settings < 0.25
            else "."
        ),
        "",
        "## Method notes",
        "",
        f"- Instant close = marked closed within {f['parameters']['instant_close_minutes']} "
        "minute; re-report = a same-category request within "
        f"{f['parameters']['rereport_radius_m']} m and {f['parameters']['rereport_window_days']}"
        " days after closing, compared with the same search before filing (placebo).",
        "- Legacy requests still open at the cutover never close in the legacy data, so the "
        '"before" year ends 30 days before the relaunch and time to close is compared as '
        '"closed within N days", not as a median of closed requests.',
        "- Rates are computed from counts in the served marts through metrics.yml, the same path "
        "the dashboard and the Ask agent use.",
        "",
    ]
    return "\n".join(lines)


def write(findings: dict, path: Path = OUT) -> None:
    path.write_text(render(findings))
