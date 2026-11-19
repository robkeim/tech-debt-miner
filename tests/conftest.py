import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import time_machine
from hypothesis import HealthCheck, settings

from support.tiers import tier_errors

TESTS_ROOT = Path(__file__).parent
FROZEN_NOW = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)

settings.register_profile(
    "ci",
    derandomize=True,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("ci" if os.environ.get("CI") else "default")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    errors = tier_errors(
        (
            (item.nodeid, Path(item.path), {mark.name for mark in item.iter_markers()})
            for item in items
        ),
        TESTS_ROOT,
    )
    if errors:
        raise pytest.UsageError("tier marker violations:\n" + "\n".join(errors))


@pytest.fixture(autouse=True)
def frozen_clock() -> Iterator[time_machine.Traveller]:
    """Freeze the clock at FROZEN_NOW. Tests can call `.move_to(...)` to override it."""
    with time_machine.travel(FROZEN_NOW, tick=False) as traveller:
        yield traveller
