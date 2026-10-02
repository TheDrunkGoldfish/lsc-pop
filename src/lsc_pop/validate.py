"""Validation checks (brief section 10) and external comparators.

Checks are implemented across Phases 3-8. Comparators (e.g. OHID trust catchment figures, or local
data such as GP-registered population by ethnicity) register themselves here so they can be added
without touching the pipeline core.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    description: str
    passed: bool
    tolerance: float | None = None
    metrics: dict[str, Any] | None = None
    details: str = ""


class ValidationFailed(AssertionError):
    """A hard validation check failed; the pipeline stops."""


def check(
    ctx: Any,
    check_id: str,
    description: str,
    passed: bool,
    *,
    stage: str,
    hard: bool = True,
    tolerance: float | None = None,
    metrics: dict[str, Any] | None = None,
    details: str = "",
) -> CheckResult:
    """Record a check in ``outputs/<run_id>/validation.jsonl``; raise if a hard check fails."""
    result = CheckResult(check_id, description, bool(passed), tolerance, metrics, details)
    ctx.append_check({"stage": stage, "hard": hard, **vars(result)})
    if hard and not passed:
        raise ValidationFailed(f"[{check_id}] {description}: {details or metrics}")
    return result


Comparator = Callable[[pd.DataFrame], pd.DataFrame]
"""Takes model output; returns a tidy comparison table (keys, modelled, comparator, diff)."""

_COMPARATORS: dict[str, Comparator] = {}


def register_comparator(name: str) -> Callable[[Comparator], Comparator]:
    def deco(fn: Comparator) -> Comparator:
        if name in _COMPARATORS:
            raise ValueError(f"comparator {name!r} already registered")
        _COMPARATORS[name] = fn
        return fn

    return deco


def comparators() -> dict[str, Comparator]:
    return dict(_COMPARATORS)
