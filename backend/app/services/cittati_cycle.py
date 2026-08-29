from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IngestionRun
from app.services.cittati_ingestion import (
    CittatiVehicleSource,
    ingest_cittati_vehicles,
)
from app.services.vehicle_eta_snapshot import (
    VehicleEtaSnapshotRefreshResult,
    refresh_vehicle_eta_snapshots,
)


@dataclass(frozen=True, slots=True)
class CittatiCycleResult:
    ingestion_run: IngestionRun
    snapshot: VehicleEtaSnapshotRefreshResult | None

    @property
    def succeeded(self) -> bool:
        return self.ingestion_run.status in {"succeeded", "partial"}


async def run_cittati_cycle(
    session: AsyncSession,
    source: CittatiVehicleSource,
    *,
    queried_at: datetime | None = None,
) -> CittatiCycleResult:
    ingestion_run = await ingest_cittati_vehicles(session, source)
    snapshot = None
    if ingestion_run.status in {"succeeded", "partial"}:
        snapshot = await refresh_vehicle_eta_snapshots(
            session,
            queried_at=queried_at or datetime.now(UTC),
        )
        await session.commit()
    return CittatiCycleResult(
        ingestion_run=ingestion_run,
        snapshot=snapshot,
    )
