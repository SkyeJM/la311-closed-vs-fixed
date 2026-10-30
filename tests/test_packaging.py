"""The portfolio documents: rendered from the numbers, never typed by hand (brief section 9)."""

import re

import pytest
import yaml

from ai.agent import numbers
from findings import packaging

ROOT = packaging.ROOT
# Digits that aren't numbers: the service's name, an audit's title, model names, list numbering.
NAMES = [
    r"The 411 on 311",
    r"\b311\b",
    r"claude-(?:haiku|sonnet|opus)-\d+-\d+",
    r"(?:Haiku|Sonnet|Opus) \d+\.\d+",
    r"(?m)^\**\d+\.\s",
]


def test_the_documents_are_rendered_from_the_numbers():
    """`make packaging` was run after the last change to a template or to the numbers."""
    for name, text in packaging.render().items():
        assert packaging.OUTPUTS[name].read_text() == text, f"{name} is stale: make packaging"


def definitions() -> list[float]:
    """Numbers that are definitions, not findings (30 days, 50 m, 12-month windows)."""
    findings = packaging.load()[0]
    return numbers.pool(yaml.safe_load((ROOT / "metrics.yml").read_text())) + numbers.pool(
        findings["parameters"]
    )


@pytest.mark.parametrize("name", sorted(packaging.OUTPUTS))
def test_templates_type_no_numbers(name):
    """Every data number comes from a {placeholder}; the prose itself may hold only years,
    small counts and definitions."""
    text = (packaging.TEMPLATES / name).read_text()
    text = re.sub(r"```.*?```", " ", text, flags=re.S)  # code and the diagram
    text = re.sub(r"\{\w+\}", " ", text)
    text = re.sub(r"\]\([^)]*\)|https?://\S+", " ", text)  # link targets
    for pattern in NAMES:
        text = re.sub(pattern, " ", text)
    typed = numbers.unsupported(text, definitions())
    assert not typed, f"{name} types numbers by hand: {typed}"
