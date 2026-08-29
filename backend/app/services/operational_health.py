from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

OperationalState = Literal["operational", "degraded", "starting"]


@dataclass(frozen=True, slots=True)
class CittatiOperationalStatus:
    status: OperationalState
    latest_attempt_status: str | None
    last_success_at: datetime | None
    last_success_age_seconds: float | None


async def query_cittati_operational_status(
    session: AsyncSession,
    *,
    now: datetime,
    stale_after_seconds: float,
) -> CittatiOperationalStatus:
    if now.tzinfo is None:
        raise ValueError("Operational health timestamp must include a timezone.")
    if stale_after_seconds <= 0:
        raise ValueError("Operational stale threshold must be positive.")

    result = await session.execute(
        text(
            """
            SELECT
                (
                    SELECT status
                    FROM audit.ingestion_runs
                    WHERE source_system = 'cittati'
                      AND resource_name = 'operacional/veiculos'
                    ORDER BY started_at DESC
                    LIMIT 1
                ) AS latest_attempt_status,
                (
                    SELECT finished_at
                    FROM audit.ingestion_runs
                    WHERE source_system = 'cittati'
                      AND resource_name = 'operacional/veiculos'
                      AND status IN ('succeeded', 'partial')
                    ORDER BY finished_at DESC
                    LIMIT 1
                ) AS last_success_at
            """
        )
    )
    row = result.mappings().one()
    last_success_at = row["last_success_at"]
    if last_success_at is None:
        return CittatiOperationalStatus(
            status="starting",
            latest_attempt_status=row["latest_attempt_status"],
            last_success_at=None,
            last_success_age_seconds=None,
        )

    age_seconds = max(0.0, (now - last_success_at).total_seconds())
    latest_failed = row["latest_attempt_status"] == "failed"
    operational = age_seconds <= stale_after_seconds and not latest_failed
    return CittatiOperationalStatus(
        status="operational" if operational else "degraded",
        latest_attempt_status=row["latest_attempt_status"],
        last_success_at=last_success_at,
        last_success_age_seconds=age_seconds,
    )
