"""Every number in an answer must come from a tool result: extraction and the check.

The rule (brief section 6) is checked in code twice: at runtime, before an answer is accepted,
and again in the evals. A number in the answer is supported when some value the tools returned
rounds to it at the precision it was written with, read as is, as a percentage (x 100), as days
from hours (/ 24), or with a thousand or million multiplier. Numbers that aren't data are
exempt: years and dates, small bare counts ("top 5"), and anything in the question or in the
system prompt's definitions ("within 50 m and 30 days").
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

# Strip what can hold digits without being a number: code spans, identifiers such as
# closed_within_7d_rate, ISO dates, month-year and times.
_NOISE = [
    re.compile(r"`[^`]*`"),
    re.compile(r"\b[A-Za-z_]+\d+[A-Za-z_]+\w*\b|\b[A-Za-z]+_\w+\b"),
    re.compile(r"\b\d{4}-\d{2}(?:-\d{2})?(?:[T ]\d{2}:\d{2}(?::\d{2})?)?\b"),
    re.compile(r"\b\d{1,2}:\d{2}\b"),
    re.compile(r"\bQ[1-4]\b"),
]
_NUMBER = re.compile(
    r"(?<![\w.,])(?P<sign>[-−+])?(?P<int>\d{1,3}(?:,\d{3})+|\d+)(?:[.](?P<frac>\d+))?"
    r"(?P<comma_frac>,\d{1,2}(?!\d))?"
    r"\s?(?P<unit>%|percent\b|por ciento\b|pts?\b|points?\b|puntos?\b|pp\b|"
    r"million\b|millones\b|millón\b|(?-i:M|K)\b|thousand\b|mil\b)?",
    re.IGNORECASE,
)
_MULTIPLIERS = {"million": 1e6, "millones": 1e6, "millón": 1e6, "m": 1e6, "thousand": 1e3}
_MULTIPLIERS |= {"k": 1e3, "mil": 1e3}
_PERCENT = {"%", "percent", "por ciento"}
SMALL_COUNT = 10  # bare whole numbers up to this are exempt ("top 5", "3 categories")


@dataclass(frozen=True)
class Number:
    text: str
    value: float
    decimals: int
    percent: bool
    multiplier: float = 1.0


def extract(text: str) -> list[Number]:
    """The numbers written in a piece of prose, with the precision they were written at."""
    for pattern in _NOISE:
        text = pattern.sub(" ", text)
    numbers = []
    for m in _NUMBER.finditer(text):
        whole = m["int"].replace(",", "")
        frac = m["frac"] or (m["comma_frac"] or "")[1:]
        unit = (m["unit"] or "").lower()
        value = float(f"{whole}.{frac}" if frac else whole)
        if m["sign"] in ("-", "−"):
            value = -value
        multiplier = _MULTIPLIERS.get(unit, 1.0)
        numbers.append(Number(m.group(0).strip(), value, len(frac), unit in _PERCENT, multiplier))
    return numbers


def exempt(number: Number) -> bool:
    if number.multiplier != 1.0 or number.percent or number.decimals:
        return False
    if 1990 <= number.value <= 2035:  # a year
        return True
    return 0 <= number.value <= SMALL_COUNT


def pool(values) -> list[float]:
    """Every number inside tool results (nested dicts and lists), as floats."""
    found: list[float] = []

    def walk(item):
        if isinstance(item, bool) or item is None:
            return
        if isinstance(item, int | float):
            if math.isfinite(item):
                found.append(float(item))
        elif isinstance(item, dict):
            for v in item.values():
                walk(v)
        elif isinstance(item, list | tuple):
            for v in item:
                walk(v)
        elif isinstance(item, str):
            found.extend(n.value * n.multiplier for n in extract(item))

    walk(values)
    return found


def _within(number: Number, reading: float) -> bool:
    """Does `reading` round to `number` at the precision it was written with? Half a unit in
    the last place, with slack for values the tools already rounded. Signs are ignored: prose
    says "fell 3.5 points" for a difference of -3.5."""
    target = abs(number.value) * number.multiplier
    step = 10**-number.decimals * number.multiplier
    return abs(abs(reading) - target) <= 0.5 * step * 1.02 + 1e-9


def _matches(number: Number, candidate: float) -> bool:
    readings = [candidate]
    if number.multiplier == 1.0:
        readings += [candidate * 100, candidate / 24]  # as a percentage; hours as days
    return any(_within(number, r) for r in readings)


def supports(value: float, unit: str, candidates: list[float]) -> bool:
    """Is a key number, stated in `unit`, among these values? Stricter than prose: a percent
    must be on the 0-100 scale (62.1, not 0.621), and only hours convert to days."""
    text = repr(float(value))
    decimals = 0 if text.endswith(".0") else len(text.split(".")[1])
    number = Number(text, float(value), decimals, unit == "percent")
    for c in candidates:
        if unit == "percent":
            readings = [c * 100] + ([c] if abs(c) > 1 else [])
        elif unit == "days":
            readings = [c, c / 24]
        else:
            readings = [c]
        if any(_within(number, r) for r in readings):
            return True
    return False


def unsupported(text: str, supported: list[float]) -> list[str]:
    """The numbers in `text` that no supported value accounts for."""
    return [
        n.text
        for n in extract(text)
        if not exempt(n) and not any(_matches(n, c) for c in supported)
    ]
