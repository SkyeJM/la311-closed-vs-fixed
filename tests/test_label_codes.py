"""Resolution-code labeling: parsing, escalation, the spend cap, review order and finalize.

Offline: a scripted fake client stands in for the Anthropic API.
"""

import json
from types import SimpleNamespace
from typing import get_args

import anthropic
import httpx
import pytest

from ai import label_codes as lc
from ai import pricing


def context(code: str, departments=("LASAN",), types=("Item Pickups",), service_cases=100) -> dict:
    return {
        "resolution_code": code,
        "cases": service_cases,
        "service_cases": service_cases,
        "first_seen": "2025-03-28",
        "last_seen": "2026-10-01",
        "statuses": {"Closed": 1.0},
        "departments": [{"department": d, "cases": 50} for d in departments],
        "request_types": [
            {"request_type": t, "cases": 50, "is_service_request": True} for t in types
        ],
        "contexts": [{"department": departments[0], "request_type": types[0], "cases": 50}],
        "hours_to_close": {"median": 30.0, "share_within_1_min": 0.0},
        "reason_codes": {"share_of_cases_with_one": 0.0, "top": []},
        "sibling_codes": [],
    }


def label(outcome="fixed_work_done", counts="yes", confidence="high", overrides=()) -> dict:
    return {
        "outcome_class": outcome,
        "counts_as_fixed": counts,
        "needs_context_override": bool(overrides),
        "context_overrides": list(overrides),
        "confidence": confidence,
        "rationale": f"The code says {outcome}.",
    }


class FakeClient:
    """Answers from a script, {(code, model): [answer, ...]}, consumed in call order."""

    def __init__(self, script: dict):
        self.script = {key: list(answers) for key, answers in script.items()}
        self.calls: list[tuple[str, str]] = []
        self.messages = SimpleNamespace(create=self.create)

    def create(self, *, model, messages, system, output_config, **kwargs):
        assert system[0]["cache_control"] == {"type": "ephemeral"}
        assert output_config["format"]["schema"] == lc.LABEL_SCHEMA
        code = json.loads(messages[0]["content"].split("\n", 1)[1])["resolution_code"]
        self.calls.append((code, model))
        answer = self.script[(code, model)].pop(0)
        usage = SimpleNamespace(
            input_tokens=500,
            output_tokens=300,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=4_000,
            cache_creation=None,
        )
        text = answer if isinstance(answer, str) else json.dumps(answer)
        return SimpleNamespace(
            stop_reason="end_turn", usage=usage, content=[SimpleNamespace(type="text", text=text)]
        )


H, S = lc.LABEL_MODEL, lc.ESCALATION_MODEL


def run(script: dict, contexts: dict, max_usd: float = 1.0):
    client = FakeClient(script)
    rows, summary = lc.label_codes(
        client, contexts, list(contexts), max_usd=max_usd, workers=2, log_path=None
    )
    return client, {r["resolution_code"]: r for r in rows if not r["department"]}, summary


def test_labeler_classes_are_the_seed_classes_minus_status_only_ones():
    seed = set(lc.counts_as_fixed_by_class())
    assert set(get_args(lc.OutcomeClass)) == seed - lc.STATUS_ONLY_CLASSES
    assert seed >= lc.STATUS_ONLY_CLASSES


def test_schema_is_strict_for_structured_outputs():
    objects = [lc.LABEL_SCHEMA, *lc.LABEL_SCHEMA["$defs"].values()]
    for obj in objects:
        assert obj["additionalProperties"] is False
        assert set(obj["required"]) == set(obj["properties"])


def test_agreeing_runs_keep_haiku_and_doubt_goes_to_sonnet():
    contexts = {c: context(c) for c in ["A-Agree", "B-Disagree", "C-Unsure", "D-Contradict"]}
    client, rows, summary = run(
        {
            ("A-Agree", H): [label(), label()],
            ("B-Disagree", H): [label(), label("not_found", "no")],
            ("B-Disagree", S): [label("not_found", "no")],
            ("C-Unsure", H): [label(confidence="low"), label()],
            ("C-Unsure", S): [label("deferred", "no")],
            ("D-Contradict", H): [label("cancelled", "yes"), label("cancelled", "yes")],
            ("D-Contradict", S): [label("cancelled", "no")],
        },
        contexts,
    )
    assert sorted(code for code, model in client.calls if model == S) == [
        "B-Disagree",
        "C-Unsure",
        "D-Contradict",
    ]
    assert (rows["A-Agree"]["closure_outcome"], rows["A-Agree"]["label_model"]) == (
        "fixed_work_done",
        H,
    )
    assert rows["B-Disagree"]["escalation_reason"] == "runs disagreed"
    assert (rows["C-Unsure"]["closure_outcome"], rows["C-Unsure"]["label_model"]) == ("deferred", S)
    assert rows["D-Contradict"]["escalation_reason"] == "class and counts_as_fixed contradict"
    assert summary["escalations"] == {
        "runs disagreed": 1,
        "low confidence": 1,
        "class and counts_as_fixed contradict": 1,
    }
    assert summary["escalation_chose_a_new_class"] == 1  # only C: deferred


def test_unusable_output_counts_as_a_failed_run_and_escalates():
    contexts = {"E-Odd": context("E-Odd")}
    _, rows, summary = run(
        {
            ("E-Odd", H): [
                "not json",
                label(
                    overrides=[
                        {
                            "department": "Nowhere",
                            "request_type": None,
                            "outcome_class": "unable",
                            "rationale": "?",
                        }
                    ]
                ),
            ],
            ("E-Odd", S): [label("info_only", "not_a_service")],
        },
        contexts,
    )
    assert rows["E-Odd"]["escalation_reason"] == "a run failed"
    assert rows["E-Odd"]["closure_outcome"] == "info_only"
    assert summary["failed_calls"] == 2


def test_context_overrides_become_their_own_rows():
    contexts = {"F-Mixed": context("F-Mixed", departments=("LASAN", "BSS"))}
    override = {
        "department": "BSS",
        "request_type": None,
        "outcome_class": "referred_out_of_scope",
        "rationale": "BSS uses it for referrals.",
    }
    client = FakeClient({("F-Mixed", H): [label(overrides=[override])] * 2})
    rows, _ = lc.label_codes(client, contexts, ["F-Mixed"], max_usd=1, workers=1, log_path=None)
    assert [(r["department"], r["closure_outcome"]) for r in rows] == [
        ("", "fixed_work_done"),
        ("BSS", "referred_out_of_scope"),
    ]


def test_spend_cap_stops_new_requests():
    contexts = {c: context(c) for c in ["G-One", "H-Two"]}
    script = {(c, H): [label(), label()] for c in contexts}
    # Each fake call costs $0.00024, so the cap is reached after the first (solo) call.
    client, rows, summary = run(script, contexts, max_usd=0.0001)
    assert client.calls == [("G-One", H)]
    assert summary["cost_usd"] == pytest.approx(0.0002)
    assert rows["G-One"]["closure_outcome"] == "fixed_work_done"
    assert summary["unlabeled_codes"] == ["H-Two"]


def test_an_account_refusal_stops_the_run_at_the_first_call():
    class Broke(FakeClient):
        def create(self, **kwargs):
            self.calls.append(("refused", kwargs["model"]))
            response = httpx.Response(
                400, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
            )
            raise anthropic.BadRequestError(
                "Your credit balance is too low to access the Anthropic API.",
                response=response,
                body=None,
            )

    client = Broke({})
    contexts = {c: context(c) for c in ["A-One", "B-Two", "C-Three"]}
    with pytest.raises(lc.AccountError, match="credit balance"):
        lc.label_codes(client, contexts, list(contexts), max_usd=1, workers=2, log_path=None)
    assert len(client.calls) == 1  # the solo first call; nothing after it reaches the API


def test_review_order_and_finalize_label_sources():
    contexts = {
        "AR-Request Completed": context("AR-Request Completed", service_cases=50_000),
        "X-Rare": context("X-Rare", service_cases=10),
        "Y-Big": context("Y-Big", service_cases=5_000),
    }
    proposed = [
        {
            "resolution_code": code,
            "department": "",
            "request_type": "",
            "closure_outcome": out,
            "counts_as_fixed": "",
            "confidence": conf,
            "label_model": H,
            "escalation_reason": "",
            "rationale": "r",
            "service_cases": contexts[code]["service_cases"],
        }
        for code, out, conf in [
            ("AR-Request Completed", "closed_unspecified", "high"),  # differs from the brief
            ("X-Rare", "unable", "high"),
            ("Y-Big", "not_found", "high"),
        ]
    ]
    brief = {"AR-Request Completed": "fixed_work_done"}
    review = lc.build_review(proposed, contexts, brief)
    assert [r["resolution_code"] for r in review] == ["AR-Request Completed", "Y-Big", "X-Rare"]
    assert review[0]["priority"] == 1 and "brief" in review[0]["flags"]

    review[0]["your_outcome"] = "fixed_work_done"  # the reviewer overrides the AI
    review[0]["your_note"] = "Completed means done."
    final = lc.finalize_rows(review, set(get_args(lc.OutcomeClass)))
    sources = {r["resolution_code"]: r["label_source"] for r in final}
    assert sources == {
        "AR-Request Completed": "ai_overridden",
        "Y-Big": "ai_accepted",
        "X-Rare": "ai_accepted",
    }
    assert final[0]["rationale"] == "Reviewer: Completed means done."

    report = lc.agreement_report(final, review, brief, contexts)
    assert report["ai_human_agreement"]["share_of_codes"] == round(2 / 3, 4)
    assert report["ai_human_agreement"]["overrides"] == [
        {
            "resolution_code": "AR-Request Completed",
            "ai": "closed_unspecified",
            "final": "fixed_work_done",
        }
    ]
    assert report["brief_first_guesses"] == {
        "codes_compared": 1,
        "ai_matched_guess": 0,
        "final_matched_guess": 1,
    }

    review[1]["your_outcome"] = "fixed"  # not a class
    with pytest.raises(ValueError, match="not a closure_outcome class"):
        lc.finalize_rows(review, set(get_args(lc.OutcomeClass)))


def test_cost_uses_cache_prices_and_haikus_long_prompt_tier():
    usage = SimpleNamespace(
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
        cache_creation=None,
    )
    assert pricing.cost_usd("claude-sonnet-5-5", usage) == pytest.approx(12.0)
    assert pricing.cost_usd("claude-haiku-5-5", usage) == pytest.approx(3.0)  # long-prompt tier
    small = SimpleNamespace(
        input_tokens=1_000,
        output_tokens=1_000,
        cache_creation_input_tokens=10_000,
        cache_read_input_tokens=50_000,
        cache_creation=None,
    )
    expected = (1_000 * 0.10 + 10_000 * 0.125 + 50_000 * 0.01 + 1_000 * 0.50) / 1e6
    assert pricing.cost_usd("claude-haiku-5-5", small) == pytest.approx(expected)
