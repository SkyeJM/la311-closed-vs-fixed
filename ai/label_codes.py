"""AI-assisted resolution-code labeling, with a person reviewing every label (brief section 6B).

    uv run python -m ai.label_codes context          # per-code context from the warehouse
    uv run python -m ai.label_codes run --dry-run    # what a run would send, and a rough cost
    uv run python -m ai.label_codes run              # label: Haiku twice per code, Sonnet on doubt
    uv run python -m ai.label_codes review           # the review sheet, most important rows first
    uv run python -m ai.label_codes finalize         # reviewed sheet -> dbt seed + agreement report

Each code is labeled twice by claude-haiku-5-5 with structured output. It goes to
claude-sonnet-5-5 once when the runs disagree, either run is low-confidence, a label contradicts
its own counts_as_fixed, or a run failed. Nothing reaches the dbt seed until a person has
reviewed the proposal, and `finalize` records whether each label was accepted or overridden.
When the dbt test `assert_all_resolution_codes_mapped` fails on a new code, `run` (which labels
only codes without a reviewed label) and the same review step handle it.
"""

from __future__ import annotations

import csv
import json
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

import anthropic
import duckdb
import typer
from pydantic import BaseModel, ConfigDict, ValidationError

from ai import pricing
from ingest.config import ROOT  # importing it loads .env

LABELS_DIR = ROOT / "ai" / "labels"
CONTEXT_FILE = LABELS_DIR / "code_context.json"
PROPOSED_FILE = LABELS_DIR / "resolution_code_map.proposed.csv"
RUN_SUMMARY_FILE = LABELS_DIR / "run_summary.json"
REVIEW_FILE = LABELS_DIR / "review.csv"
AGREEMENT_FILE = LABELS_DIR / "agreement.json"
BRIEF_GUESSES_FILE = LABELS_DIR / "brief_first_guesses.csv"
RUNS_DIR = LABELS_DIR / "runs"  # raw call logs (gitignored)
PROMPT_FILE = ROOT / "ai" / "prompts" / "label_codes_system.md"
SEED_FILE = ROOT / "dbt" / "seeds" / "resolution_code_map.csv"
OUTCOMES_FILE = ROOT / "dbt" / "seeds" / "closure_outcomes.csv"
WAREHOUSE = ROOT / "data" / "warehouse.duckdb"

LABEL_MODEL = "claude-haiku-5-5"
ESCALATION_MODEL = "claude-sonnet-5-5"
MAX_TOKENS = {LABEL_MODEL: 4_000, ESCALATION_MODEL: 8_000}  # room for adaptive thinking

OutcomeClass = Literal[
    "fixed_work_done",
    "already_resolved",
    "duplicate",
    "not_found",
    "referred_out_of_scope",
    "deferred",
    "unable",
    "cancelled",
    "info_only",
    "closed_unspecified",
]
# handed_off is decided by the status (Reported), never by a code, so the labeler can't pick it.
STATUS_ONLY_CLASSES = {"handed_off"}
CountsAsFixed = Literal["yes", "no", "neutral", "not_a_service", "unknown"]
Confidence = Literal["high", "medium", "low"]


class ContextOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")
    department: str | None
    request_type: str | None
    outcome_class: OutcomeClass
    rationale: str


class CodeLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome_class: OutcomeClass
    counts_as_fixed: CountsAsFixed
    needs_context_override: bool
    context_overrides: list[ContextOverride]
    confidence: Confidence
    rationale: str


LABEL_SCHEMA = anthropic.transform_schema(CodeLabel)


def counts_as_fixed_by_class() -> dict[str, str]:
    with OUTCOMES_FILE.open() as f:
        return {row["closure_outcome"]: row["counts_as_fixed"] for row in csv.DictReader(f)}


# --- context -------------------------------------------------------------------------------

_CURRENT_CODES = (
    "from intermediate.int_requests_unified where era = 'current' and resolution_code is not null"
)


def _top(con: duckdb.DuckDBPyConnection, column: str, limit: int) -> dict[str, list[tuple]]:
    rows = con.execute(
        f"""
        select resolution_code, {column}, count(*) as cases, bool_and(is_service_request)
        {_CURRENT_CODES} and {column.split(",")[0]} is not null
        group by resolution_code, {column}
        qualify row_number() over (
            partition by resolution_code order by count(*) desc, {column}
        ) <= {limit}
        order by resolution_code, cases desc
        """
    ).fetchall()
    grouped: dict[str, list[tuple]] = defaultdict(list)
    for code, *rest in rows:
        grouped[code].append(tuple(rest))
    return grouped


def build_contexts(warehouse: Path = WAREHOUSE) -> dict:
    """What the labeler sees for each code: who uses it, for what, how fast, and with what status.
    Aggregates only; no case IDs, addresses or free text."""
    con = duckdb.connect(str(warehouse), read_only=True)
    totals = con.execute(
        f"""
        select
            resolution_code,
            count(*),
            count(*) filter (where is_service_request),
            cast(min(created_at) as date),
            cast(max(created_at) as date),
            median(hours_to_close) filter (where is_terminal and hours_to_close >= 0),
            avg(case when hours_to_close <= 1.0 / 60 then 1.0 else 0.0 end)
                filter (where is_terminal and hours_to_close >= 0),
            avg(case when reason_code is not null then 1.0 else 0.0 end)
        {_CURRENT_CODES}
        group by resolution_code
        """
    ).fetchall()
    statuses = _top(con, "status", 10)
    departments = _top(con, "department", 6)
    request_types = _top(con, "request_type", 8)
    pairs = _top(con, "department, request_type", 8)
    reasons = _top(con, "reason_code", 5)
    data_end = con.execute(
        "select cast(max(created_at) as date) from intermediate.int_requests_unified"
    ).fetchone()[0]
    con.close()

    prefixes: dict[str, list[str]] = defaultdict(list)
    for code, *_ in totals:
        prefixes[code.split("-", 1)[0]].append(code)
    codes = []
    for code, cases, service, first, last, median_h, instant, with_reason in totals:
        codes.append(
            {
                "resolution_code": code,
                "cases": cases,
                "service_cases": service,
                "first_seen": str(first),
                "last_seen": str(last),
                "statuses": {s: round(n / cases, 3) for s, n, _ in statuses[code]},
                "departments": [{"department": d, "cases": n} for d, n, _ in departments[code]],
                "request_types": [
                    {"request_type": t, "cases": n, "is_service_request": svc}
                    for t, n, svc in request_types[code]
                ],
                "contexts": [
                    {"department": d, "request_type": t, "cases": n} for d, t, n, _ in pairs[code]
                ],
                "hours_to_close": {
                    "median": None if median_h is None else round(median_h, 1),
                    "share_within_1_min": None if instant is None else round(instant, 3),
                },
                "reason_codes": {
                    "share_of_cases_with_one": round(with_reason, 3),
                    "top": [{"reason_code": r, "cases": n} for r, n, _ in reasons[code]],
                },
                "sibling_codes": sorted(c for c in prefixes[code.split("-", 1)[0]] if c != code),
            }
        )
    codes.sort(key=lambda c: (-c["service_cases"], -c["cases"], c["resolution_code"]))
    return {"data_end": str(data_end), "codes": codes}


def load_contexts() -> dict[str, dict]:
    if not CONTEXT_FILE.exists():
        raise typer.BadParameter("no code context yet: run `python -m ai.label_codes context`")
    return {c["resolution_code"]: c for c in json.loads(CONTEXT_FILE.read_text())["codes"]}


def system_prompt(contexts: dict[str, dict]) -> str:
    lines = [
        f"{c['resolution_code']} | {c['service_cases']:,} | "
        f"{c['departments'][0]['department'] if c['departments'] else '(none)'}"
        for c in contexts.values()
    ]
    return PROMPT_FILE.read_text().replace("{code_list}", "\n".join(lines))


def user_message(context: dict) -> str:
    return "Label this resolution code. Its context:\n" + json.dumps(context, indent=1)


# --- labeling ------------------------------------------------------------------------------


@dataclass
class CallResult:
    code: str
    model: str
    run: int
    label: CodeLabel | None
    error: str | None
    cost_usd: float
    seconds: float
    usage: dict

    def outcome(self) -> str:
        return self.label.outcome_class if self.label else "error"


def parse_label(response, context: dict) -> tuple[CodeLabel | None, str | None]:
    if response.stop_reason in ("refusal", "max_tokens"):
        return None, f"stopped: {response.stop_reason}"
    text = next((block.text for block in response.content if block.type == "text"), None)
    if text is None:
        return None, "no text block in the response"
    try:
        raw = json.loads(text)
        # Enum values can come back with different capitalization (structured-outputs docs).
        for key in ("outcome_class", "counts_as_fixed", "confidence"):
            if isinstance(raw.get(key), str):
                raw[key] = raw[key].lower()
        label = CodeLabel.model_validate(raw)
    except (json.JSONDecodeError, ValidationError) as exc:
        return None, f"output didn't match the schema: {str(exc)[:200]}"
    departments = {d["department"] for d in context["departments"]}
    request_types = {t["request_type"] for t in context["request_types"]}
    for override in label.context_overrides:
        named = override.department or override.request_type
        if (
            not named
            or (override.department and override.department not in departments)
            or (override.request_type and override.request_type not in request_types)
        ):
            return None, "a context override names a department or type that isn't in the context"
    return label, None


class Labeler:
    """Sends one labeling request per (code, model, run), with a cached system prompt, a spend
    cap and a JSONL log of every call."""

    def __init__(self, client, contexts: dict[str, dict], max_usd: float, log_path: Path | None):
        self.client = client
        self.contexts = contexts
        self.system = [
            {
                "type": "text",
                "text": system_prompt(contexts),
                "cache_control": {"type": "ephemeral"},
            }
        ]
        self.max_usd = max_usd
        self.spent = 0.0
        self.log_path = log_path
        self._lock = threading.Lock()

    def call(self, code: str, model: str, run: int) -> CallResult:
        context = self.contexts[code]
        if self.spent >= self.max_usd:
            return CallResult(code, model, run, None, "spend cap reached", 0.0, 0.0, {})
        start = time.monotonic()
        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=MAX_TOKENS.get(model, 8_000),
                system=self.system,
                messages=[{"role": "user", "content": user_message(context)}],
                output_config={"format": {"type": "json_schema", "schema": LABEL_SCHEMA}},
                thinking={"type": "adaptive"},
            )
        except anthropic.APIError as exc:
            result = CallResult(
                code, model, run, None, f"{type(exc).__name__}: {exc}"[:300], 0.0, 0.0, {}
            )
        else:
            label, error = parse_label(response, context)
            usage = response.usage
            cost = pricing.cost_usd(model, usage)
            with self._lock:
                self.spent += cost
            result = CallResult(
                code,
                model,
                run,
                label,
                error,
                cost,
                round(time.monotonic() - start, 2),
                {
                    name: getattr(usage, name, None) or 0
                    for name in (
                        "input_tokens",
                        "cache_creation_input_tokens",
                        "cache_read_input_tokens",
                        "output_tokens",
                    )
                },
            )
        self._log(result)
        return result

    def _log(self, result: CallResult) -> None:
        if self.log_path is None:
            return
        record = asdict(result) | {"label": result.label.model_dump() if result.label else None}
        with self._lock, self.log_path.open("a") as f:
            f.write(json.dumps(record) + "\n")

    def run_all(self, jobs: list[tuple[str, str, int]], workers: int) -> list[CallResult]:
        """The first call goes alone, so the cached system prompt exists before the rest start
        (a cache entry is readable only once the first response begins)."""
        if not jobs:
            return []
        first = self.call(*jobs[0])
        with ThreadPoolExecutor(max_workers=workers) as pool:
            rest = list(pool.map(lambda job: self.call(*job), jobs[1:]))
        return [first, *rest]


def _overrides(label: CodeLabel) -> frozenset:
    return frozenset(
        (o.department, o.request_type, o.outcome_class) for o in label.context_overrides
    )


def escalation_reason(runs: list[CallResult], counts_as_fixed: dict[str, str]) -> str | None:
    labels = [r.label for r in runs]
    if any(label is None for label in labels):
        return "a run failed"
    if len({label.outcome_class for label in labels}) > 1:
        return "runs disagreed"
    if any(label.confidence == "low" for label in labels):
        return "low confidence"
    if any(label.counts_as_fixed != counts_as_fixed[label.outcome_class] for label in labels):
        return "class and counts_as_fixed contradict"
    if len({_overrides(label) for label in labels}) > 1:
        return "context overrides disagreed"
    return None


PROPOSED_COLUMNS = [
    "resolution_code",
    "department",
    "request_type",
    "closure_outcome",
    "counts_as_fixed",
    "confidence",
    "label_model",
    "escalation_reason",
    "haiku_run_1",
    "haiku_run_2",
    "escalation_label",
    "rationale",
    "service_cases",
]


def propose(
    contexts: dict[str, dict],
    first_pass: dict[str, list[CallResult]],
    escalated: dict[str, CallResult],
    reasons: dict[str, str],
    counts_as_fixed: dict[str, str],
) -> list[dict]:
    """One code-level row per code, plus a row per context override. The escalation model's
    label wins when there was one; otherwise both first-pass runs agree and run 1 is used."""
    rows = []
    for code, runs in first_pass.items():
        chosen = escalated.get(code)
        if chosen is None or chosen.label is None:
            chosen = next((r for r in runs if r.label), None)
        base = {
            "resolution_code": code,
            "label_model": chosen.model if chosen else "",
            "escalation_reason": reasons.get(code, ""),
            "haiku_run_1": runs[0].outcome(),
            "haiku_run_2": runs[1].outcome() if len(runs) > 1 else "",
            "escalation_label": escalated[code].outcome() if code in escalated else "",
            "service_cases": contexts[code]["service_cases"],
        }
        if chosen is None:  # every call failed: a person labels it in review
            empty = dict.fromkeys(
                [
                    "department",
                    "request_type",
                    "closure_outcome",
                    "counts_as_fixed",
                    "confidence",
                    "rationale",
                ],
                "",
            )
            rows.append(base | empty)
            continue
        label = chosen.label
        rows.append(
            base
            | {
                "department": "",
                "request_type": "",
                "closure_outcome": label.outcome_class,
                "counts_as_fixed": counts_as_fixed[label.outcome_class],
                "confidence": label.confidence,
                "rationale": label.rationale,
            }
        )
        for override in label.context_overrides:
            rows.append(
                base
                | {
                    "department": override.department or "",
                    "request_type": override.request_type or "",
                    "closure_outcome": override.outcome_class,
                    "counts_as_fixed": counts_as_fixed[override.outcome_class],
                    "confidence": label.confidence,
                    "rationale": override.rationale,
                }
            )
    rows.sort(key=lambda r: (-r["service_cases"], r["resolution_code"], r["department"]))
    return rows


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def reviewed_codes() -> set[str]:
    """Codes whose code-level label has been through review."""
    return {
        row["resolution_code"]
        for row in read_csv(SEED_FILE)
        if not row["department"]
        and not row["request_type"]
        and row["label_source"] != "brief_first_guess"
    }


def label_codes(
    client,
    contexts: dict[str, dict],
    codes: list[str],
    *,
    model: str = LABEL_MODEL,
    escalation_model: str = ESCALATION_MODEL,
    max_usd: float,
    workers: int,
    log_path: Path | None,
) -> tuple[list[dict], dict]:
    counts_as_fixed = counts_as_fixed_by_class()
    labeler = Labeler(client, contexts, max_usd, log_path)
    started = time.monotonic()
    results = labeler.run_all([(c, model, run) for c in codes for run in (1, 2)], workers)
    first_pass: dict[str, list[CallResult]] = defaultdict(list)
    for result in results:
        first_pass[result.code].append(result)
    reasons = {
        code: reason
        for code, runs in first_pass.items()
        if (reason := escalation_reason(runs, counts_as_fixed))
    }
    second = labeler.run_all([(c, escalation_model, 1) for c in reasons], workers)
    escalated = {r.code: r for r in second}
    rows = propose(contexts, first_pass, escalated, reasons, counts_as_fixed)
    calls = results + second
    summary = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "models": {"label": model, "escalation": escalation_model},
        "codes": len(codes),
        "calls": len(calls),
        "failed_calls": sum(r.label is None for r in calls),
        "first_pass_runs_agreed": sum(
            len({r.outcome() for r in runs}) == 1 for runs in first_pass.values()
        ),
        "escalations": dict(Counter(reasons.values())),
        # Escalated codes where the second model picked a class neither first-pass run had.
        "escalation_chose_a_new_class": sum(
            1
            for code, r in escalated.items()
            if r.label and r.outcome() not in {run.outcome() for run in first_pass[code]}
        ),
        "unlabeled_codes": sorted(r["resolution_code"] for r in rows if not r["closure_outcome"]),
        "cost_usd": round(labeler.spent, 4),
        "max_usd": max_usd,
        "tokens": {
            name: sum(r.usage.get(name, 0) for r in calls)
            for name in (
                "input_tokens",
                "cache_creation_input_tokens",
                "cache_read_input_tokens",
                "output_tokens",
            )
        },
        "seconds": round(time.monotonic() - started, 1),
    }
    return rows, summary


# --- review and finalize -------------------------------------------------------------------

REVIEW_COLUMNS = [
    "priority",
    "flags",
    "resolution_code",
    "department",
    "request_type",
    "service_cases",
    "used_by",
    "statuses",
    "ai_outcome",
    "ai_confidence",
    "ai_model",
    "ai_rationale",
    "brief_first_guess",
    "your_outcome",
    "your_note",
]


def _shares(mapping: dict[str, float]) -> str:
    return ", ".join(f"{k} {v:.0%}" for k, v in mapping.items())


def build_review(
    proposed: list[dict], contexts: dict[str, dict], brief: dict[str, str]
) -> list[dict]:
    """Rows a person should look at first come first: disagreements, doubt, then volume."""
    rows = []
    for p in proposed:
        code = p["resolution_code"]
        context = contexts[code]
        is_override = bool(p["department"] or p["request_type"])
        guess = "" if is_override else brief.get(code, "")
        flags = []
        if not p["closure_outcome"]:
            flags.append("no AI label")
        if guess and guess != p["closure_outcome"]:
            flags.append("differs from the brief's first guess")
        if p["confidence"] == "low":
            flags.append("low confidence")
        if p["escalation_reason"]:
            flags.append(f"escalated ({p['escalation_reason']})")
        if is_override:
            flags.append("context override")
        if p["service_cases"] and int(p["service_cases"]) >= 1_000:
            flags.append("1,000+ service cases")
        disagrees = bool(guess) and guess != p["closure_outcome"]
        if not p["closure_outcome"] or p["confidence"] == "low" or disagrees:
            priority = 1
        elif p["escalation_reason"] or is_override:
            priority = 2
        elif int(p["service_cases"] or 0) >= 1_000:
            priority = 3
        else:
            priority = 4
        rows.append(
            {
                "priority": priority,
                "flags": "; ".join(flags),
                "resolution_code": code,
                "department": p["department"],
                "request_type": p["request_type"],
                "service_cases": p["service_cases"],
                "used_by": "; ".join(
                    f"{c['department']} / {c['request_type']} ({c['cases']:,})"
                    for c in context["contexts"][:3]
                ),
                "statuses": _shares(context["statuses"]),
                "ai_outcome": p["closure_outcome"],
                "ai_confidence": p["confidence"],
                "ai_model": p["label_model"],
                "ai_rationale": p["rationale"],
                "brief_first_guess": guess,
                "your_outcome": "",
                "your_note": "",
            }
        )
    rows.sort(key=lambda r: (r["priority"], -int(r["service_cases"] or 0), r["resolution_code"]))
    return rows


SEED_COLUMNS = [
    "resolution_code",
    "department",
    "request_type",
    "closure_outcome",
    "label_source",
    "rationale",
]


def finalize_rows(review: list[dict], valid: set[str]) -> list[dict]:
    """label_source: ai_accepted when the reviewer kept the AI label (blank or the same class),
    ai_overridden when they changed it, human when there was no AI label to review."""
    rows = []
    for r in review:
        chosen = r["your_outcome"].strip() or r["ai_outcome"]
        if chosen not in valid:
            raise ValueError(f"{r['resolution_code']}: '{chosen}' is not a closure_outcome class")
        if not r["ai_outcome"]:
            source = "human"
        elif chosen != r["ai_outcome"]:
            source = "ai_overridden"
        else:
            source = "ai_accepted"
        note = r["your_note"].strip()
        rationale = f"Reviewer: {note}" if note else f"{r['ai_model']}: {r['ai_rationale']}"
        rows.append(
            {
                "resolution_code": r["resolution_code"],
                "department": r["department"],
                "request_type": r["request_type"],
                "closure_outcome": chosen,
                "label_source": source,
                "rationale": rationale,
            }
        )
    return rows


def agreement_report(
    final: list[dict], review: list[dict], brief: dict[str, str], contexts: dict[str, dict]
) -> dict:
    ai = {
        (r["resolution_code"], r["department"], r["request_type"]): r["ai_outcome"] for r in review
    }
    code_level = [r for r in final if not r["department"] and not r["request_type"]]
    labeled = [r for r in code_level if r["label_source"] != "human"]

    def weight(row: dict) -> int:
        return contexts[row["resolution_code"]]["service_cases"]

    agreed = [r for r in labeled if r["label_source"] == "ai_accepted"]
    by_class: dict[str, dict] = {}
    for row in labeled:
        entry = by_class.setdefault(row["closure_outcome"], {"codes": 0, "ai_agreed": 0})
        entry["codes"] += 1
        entry["ai_agreed"] += row["label_source"] == "ai_accepted"
    compared = [r for r in labeled if r["resolution_code"] in brief]
    key = lambda r: (r["resolution_code"], r["department"], r["request_type"])  # noqa: E731
    return {
        "codes": len(code_level),
        "context_override_rows": len(final) - len(code_level),
        "ai_labeled_codes": len(labeled),
        "human_only_codes": len(code_level) - len(labeled),
        "ai_human_agreement": {
            "share_of_codes": round(len(agreed) / len(labeled), 4) if labeled else None,
            "share_of_service_cases": round(
                sum(map(weight, agreed)) / max(1, sum(map(weight, labeled))), 4
            ),
            "by_final_class": dict(sorted(by_class.items())),
            "overrides": [
                {
                    "resolution_code": r["resolution_code"],
                    "ai": ai[key(r)],
                    "final": r["closure_outcome"],
                }
                for r in labeled
                if r["label_source"] == "ai_overridden"
            ],
        },
        "brief_first_guesses": {
            "codes_compared": len(compared),
            "ai_matched_guess": sum(ai[key(r)] == brief[r["resolution_code"]] for r in compared),
            "final_matched_guess": sum(
                r["closure_outcome"] == brief[r["resolution_code"]] for r in compared
            ),
        },
    }


# --- CLI -----------------------------------------------------------------------------------

app = typer.Typer(
    help="Label MyLA311 resolution codes with Claude, then review them.",
    no_args_is_help=True,
    add_completion=False,
)


@app.command()
def context() -> None:
    """Write ai/labels/code_context.json: what the model sees for each code."""
    contexts = build_contexts()
    CONTEXT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONTEXT_FILE.write_text(json.dumps(contexts, indent=1) + "\n")
    typer.echo(
        f"{len(contexts['codes'])} codes (data through {contexts['data_end']}) -> "
        f"{CONTEXT_FILE.relative_to(ROOT)}"
    )


@app.command()
def run(
    codes: Annotated[
        str, typer.Option(help="'new' = codes without a reviewed label; 'all' = every code.")
    ] = "new",
    model: Annotated[str, typer.Option(help="First-pass model (two runs per code).")] = LABEL_MODEL,
    escalation_model: Annotated[str, typer.Option(help="Model for doubtful codes.")] = (
        ESCALATION_MODEL
    ),
    max_usd: Annotated[float, typer.Option(help="Stop sending requests past this spend.")] = 3.0,
    workers: Annotated[int, typer.Option(help="Concurrent requests.")] = 4,
    dry_run: Annotated[bool, typer.Option(help="Show the plan and a rough cost; no API calls.")] = (
        False
    ),
) -> None:
    """Label codes with structured output; writes the proposed map for review."""
    contexts = load_contexts()
    if codes not in ("new", "all"):
        raise typer.BadParameter("--codes must be 'new' or 'all'")
    done = set() if codes == "all" else reviewed_codes()
    selected = [c for c in contexts if c not in done]
    if not selected:
        typer.echo("Every code already has a reviewed label.")
        return
    prompt_chars = len(system_prompt(contexts))
    message_chars = sum(len(user_message(contexts[c])) for c in selected)
    if dry_run:
        # Rough: ~3.5 characters per token; 1,500 output tokens per call with thinking; one in
        # four codes escalated. The real cost is printed after a run.
        haiku = pricing.PRICES[model]
        sonnet = pricing.PRICES[escalation_model]
        est = (
            2 * len(selected) * (prompt_chars / 3.5 * haiku.cache_read + 1_500 * haiku.output)
            + 2 * message_chars / 3.5 * haiku.input
            + len(selected) / 4 * (prompt_chars / 3.5 * sonnet.cache_read + 3_000 * sonnet.output)
        ) / 1_000_000
        typer.echo(
            f"{len(selected)} codes, {2 * len(selected)} {model} calls plus escalations to "
            f"{escalation_model}. System prompt ~{prompt_chars / 3.5:,.0f} tokens (cached). "
            f"Rough cost ${est:.2f} (cap ${max_usd:.2f})."
        )
        return
    client = anthropic.Anthropic(max_retries=6)  # reads ANTHROPIC_API_KEY from .env
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    log = RUNS_DIR / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}.jsonl"
    rows, summary = label_codes(
        client,
        contexts,
        selected,
        model=model,
        escalation_model=escalation_model,
        max_usd=max_usd,
        workers=workers,
        log_path=log,
    )
    write_csv(PROPOSED_FILE, rows, PROPOSED_COLUMNS)
    RUN_SUMMARY_FILE.write_text(json.dumps(summary, indent=1) + "\n")
    typer.echo(json.dumps(summary, indent=1))
    typer.echo(f"-> {PROPOSED_FILE.relative_to(ROOT)}; call log {log.relative_to(ROOT)}")


@app.command()
def review() -> None:
    """Write ai/labels/review.csv from the proposal; fill `your_outcome` only to change a label."""
    brief = {r["resolution_code"]: r["closure_outcome"] for r in read_csv(BRIEF_GUESSES_FILE)}
    rows = build_review(read_csv(PROPOSED_FILE), load_contexts(), brief)
    write_csv(REVIEW_FILE, rows, REVIEW_COLUMNS)
    by_priority = Counter(r["priority"] for r in rows)
    typer.echo(
        f"{len(rows)} rows -> {REVIEW_FILE.relative_to(ROOT)}; by priority "
        f"{dict(sorted(by_priority.items()))}"
    )


@app.command()
def finalize() -> None:
    """Reviewed sheet -> dbt/seeds/resolution_code_map.csv, plus ai/labels/agreement.json."""
    contexts = load_contexts()
    review_rows = read_csv(REVIEW_FILE)
    valid = set(counts_as_fixed_by_class()) - STATUS_ONLY_CLASSES
    rows = finalize_rows(review_rows, valid)
    reviewed = {r["resolution_code"] for r in rows if not r["department"] and not r["request_type"]}
    kept = [
        r
        for r in read_csv(SEED_FILE)
        if r["label_source"] != "brief_first_guess" and r["resolution_code"] not in reviewed
    ]
    final = sorted(
        kept + rows, key=lambda r: (r["resolution_code"], r["department"], r["request_type"])
    )
    missing = set(contexts) - {r["resolution_code"] for r in final}
    if missing:
        raise typer.BadParameter(f"{len(missing)} codes have no label yet: {sorted(missing)[:5]}")
    write_csv(SEED_FILE, final, SEED_COLUMNS)
    brief = {r["resolution_code"]: r["closure_outcome"] for r in read_csv(BRIEF_GUESSES_FILE)}
    report = agreement_report(rows, review_rows, brief, contexts)
    if RUN_SUMMARY_FILE.exists():
        report["labeling_run"] = json.loads(RUN_SUMMARY_FILE.read_text())
    AGREEMENT_FILE.write_text(json.dumps(report, indent=1) + "\n")
    typer.echo(json.dumps(report["ai_human_agreement"] | report["brief_first_guesses"], indent=1))
    typer.echo(f"-> {SEED_FILE.relative_to(ROOT)} and {AGREEMENT_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    app()
