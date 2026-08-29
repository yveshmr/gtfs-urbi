from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable

from app.core.config import get_settings
from app.db.session import session_factory
from app.integrations.cittati import CittatiClient
from app.services.cittati_cycle import run_cittati_cycle

logger = logging.getLogger("app.worker.cittati")


def next_worker_delay_seconds(
    *,
    succeeded: bool,
    cycle_duration_seconds: float,
    poll_interval_seconds: float,
    current_backoff_seconds: float,
    maximum_backoff_seconds: float,
) -> tuple[float, float]:
    if succeeded:
        return (
            max(0.0, poll_interval_seconds - cycle_duration_seconds),
            current_backoff_seconds,
        )
    delay = min(current_backoff_seconds, maximum_backoff_seconds)
    return delay, min(current_backoff_seconds * 2, maximum_backoff_seconds)


async def run_worker_loop(
    cycle: Callable[[], Awaitable[bool]],
    *,
    stop_event: asyncio.Event,
    poll_interval_seconds: float,
    retry_initial_seconds: float,
    retry_max_seconds: float,
) -> None:
    if poll_interval_seconds <= 0:
        raise ValueError("Worker poll interval must be positive.")
    if retry_initial_seconds <= 0 or retry_max_seconds < retry_initial_seconds:
        raise ValueError("Worker retry interval configuration is invalid.")

    loop = asyncio.get_running_loop()
    backoff = retry_initial_seconds
    while not stop_event.is_set():
        started = loop.time()
        succeeded = False
        try:
            succeeded = await cycle()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Cittati worker cycle failed")

        duration = loop.time() - started
        delay, next_backoff = next_worker_delay_seconds(
            succeeded=succeeded,
            cycle_duration_seconds=duration,
            poll_interval_seconds=poll_interval_seconds,
            current_backoff_seconds=backoff,
            maximum_backoff_seconds=retry_max_seconds,
        )
        logger.info(
            "Cittati worker cycle scheduled succeeded=%s duration_seconds=%.3f "
            "next_delay_seconds=%.3f",
            succeeded,
            duration,
            delay,
        )
        backoff = retry_initial_seconds if succeeded else next_backoff
        if stop_event.is_set() or delay <= 0:
            continue
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=delay)
        except TimeoutError:
            pass


def install_shutdown_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()

    def request_shutdown() -> None:
        logger.info("Cittati worker shutdown requested")
        stop_event.set()

    for signal_number in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_number, request_shutdown)
        except NotImplementedError:
            signal.signal(
                signal_number,
                lambda signum, frame: loop.call_soon_threadsafe(request_shutdown),
            )


async def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = get_settings()
    if settings.cittati_username is None:
        raise RuntimeError("CITTATI_USER is not configured.")
    if settings.cittati_password is None:
        raise RuntimeError("CITTATI_PASS is not configured.")
    if settings.cittati_company is None:
        raise RuntimeError("CITTATI_COMPANY is not configured.")

    stop_event = asyncio.Event()
    install_shutdown_handlers(stop_event)

    async with CittatiClient(
        base_url=settings.cittati_base_url,
        username=settings.cittati_username,
        password=settings.cittati_password.get_secret_value(),
        company=settings.cittati_company,
        timeout_seconds=settings.cittati_timeout_seconds,
    ) as client:

        async def execute_cycle() -> bool:
            async with session_factory() as session:
                result = await run_cittati_cycle(session, client)
            snapshot = result.snapshot
            logger.info(
                "Cittati cycle finished status=%s records=%s snapshot_performed=%s "
                "snapshots=%s",
                result.ingestion_run.status,
                result.ingestion_run.records_received,
                snapshot.performed if snapshot is not None else False,
                snapshot.snapshot_count if snapshot is not None else 0,
            )
            return result.succeeded

        await run_worker_loop(
            execute_cycle,
            stop_event=stop_event,
            poll_interval_seconds=settings.cittati_poll_interval_seconds,
            retry_initial_seconds=settings.cittati_retry_initial_seconds,
            retry_max_seconds=settings.cittati_retry_max_seconds,
        )


if __name__ == "__main__":
    asyncio.run(run())
