from datetime import UTC, datetime

import pytest
import time_machine

pytestmark = pytest.mark.unit


def test_clock_is_frozen_by_default() -> None:
    assert datetime.now(UTC) == datetime(2024, 1, 15, 12, 0, tzinfo=UTC)


def test_clock_can_be_overridden(frozen_clock: time_machine.Traveller) -> None:
    frozen_clock.move_to(datetime(2030, 5, 5, tzinfo=UTC))
    assert datetime.now(UTC) == datetime(2030, 5, 5, tzinfo=UTC)
