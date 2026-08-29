import asyncio

import pytest
from app.cli.run_cittati_worker import (
    next_worker_delay_seconds,
    run_worker_loop,
)


def test_successful_cycle_preserves_fixed_start_to_start_interval() -> None:
    delay, next_backoff = next_worker_delay_seconds(
        succeeded=True,
        cycle_duration_seconds=3,
        poll_interval_seconds=10,
        current_backoff_seconds=8,
        maximum_backoff_seconds=30,
    )

    assert delay == 7
    assert next_backoff == 8


def test_slow_cycle_starts_next_iteration_without_overlap_delay() -> None:
    delay, _ = next_worker_delay_seconds(
        succeeded=True,
        cycle_duration_seconds=12,
        poll_interval_seconds=10,
        current_backoff_seconds=2,
        maximum_backoff_seconds=30,
    )

    assert delay == 0


def test_failed_cycle_uses_capped_exponential_backoff() -> None:
    delay, next_backoff = next_worker_delay_seconds(
        succeeded=False,
        cycle_duration_seconds=1,
        poll_interval_seconds=10,
        current_backoff_seconds=20,
        maximum_backoff_seconds=30,
    )

    assert delay == 20
    assert next_backoff == 30


@pytest.mark.asyncio
async def test_worker_never_overlaps_cycles() -> None:
    stop_event = asyncio.Event()
    active_cycles = 0
    maximum_active_cycles = 0
    cycle_count = 0

    async def cycle() -> bool:
        nonlocal active_cycles, maximum_active_cycles, cycle_count
        active_cycles += 1
        maximum_active_cycles = max(maximum_active_cycles, active_cycles)
        await asyncio.sleep(0)
        active_cycles -= 1
        cycle_count += 1
        if cycle_count == 2:
            stop_event.set()
        return True

    await run_worker_loop(
        cycle,
        stop_event=stop_event,
        poll_interval_seconds=0.001,
        retry_initial_seconds=0.001,
        retry_max_seconds=0.01,
    )

    assert cycle_count == 2
    assert maximum_active_cycles == 1
