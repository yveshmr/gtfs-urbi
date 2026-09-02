from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IngestionRun
from app.services.active_trip_index import ActiveTripIndex, load_active_trip_index
from app.services.cittati_ingestion import (
    CittatiVehicleSource,
    ingest_cittati_vehicles,
)
from app.services.planned_eta_snapshot import (
    PlannedEtaSnapshotRefreshResult,
    refresh_missing_planned_eta_snapshots,
)
from app.services.segment_aggregation import operational_service_date
from app.services.vehicle_eta_snapshot import (
    VehicleEtaSnapshotRefreshResult,
    refresh_vehicle_eta_snapshots,
)


@dataclass(frozen=True, slots=True)
class CittatiCycleResult:
    ingestion_run: IngestionRun
    snapshot: VehicleEtaSnapshotRefreshResult | None
    planned_snapshot: PlannedEtaSnapshotRefreshResult | None

    @property
    def succeeded(self) -> bool:
        return self.ingestion_run.status in {"succeeded", "partial"}


async def run_cittati_cycle(
    session: AsyncSession,
    source: CittatiVehicleSource,
    *,
    queried_at: datetime | None = None,
    active_trip_index: ActiveTripIndex | None = None,
) -> CittatiCycleResult:
    evaluated_at = queried_at or datetime.now(UTC)
    trip_index = active_trip_index
    if trip_index is None:
        trip_index = await load_active_trip_index(
            session,
            service_date=operational_service_date(evaluated_at),
        )
    ingestion_run = await ingest_cittati_vehicles(
        session,
        source,
        active_trip_index=trip_index,
    )
    snapshot = None
    planned_snapshot = None
    if ingestion_run.status in {"succeeded", "partial"}:
        snapshot = await refresh_vehicle_eta_snapshots(
            session,
            queried_at=evaluated_at,
        )
        planned_snapshot = await refresh_missing_planned_eta_snapshots(
            session,
            queried_at=evaluated_at,
            active_trip_index=trip_index,
        )
        await session.commit()
    return CittatiCycleResult(
        ingestion_run=ingestion_run,
        snapshot=snapshot,
        planned_snapshot=planned_snapshot,
    )
