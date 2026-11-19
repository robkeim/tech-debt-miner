"""Helpers for asserting on gate step lists."""

from collections.abc import Sequence

from gate.models import Skipped, Step


def step_names(steps: Sequence[Step | Skipped]) -> list[str]:
    return [step.name for step in steps]
