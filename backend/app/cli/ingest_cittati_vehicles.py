import asyncio
from datetime import UTC, datetime

from app.core.config import get_settings
from app.db.session import session_factory
from app.integrations.cittati import CittatiClient
from app.services.cittati_ingestion import ingest_cittati_vehicles
from app.services.vehicle_eta_snapshot import refresh_vehicle_eta_snapshots


async def run() -> None:
    settings = get_settings()
    if settings.cittati_username is None:
        raise RuntimeError("CITTATI_USER is not configured.")
    if settings.cittati_password is None:
        raise RuntimeError("CITTATI_PASS is not configured.")
    if settings.cittati_company is None:
        raise RuntimeError("CITTATI_COMPANY is not configured.")

    async with CittatiClient(
        base_url=settings.cittati_base_url,
        username=settings.cittati_username,
        password=settings.cittati_password.get_secret_value(),
        company=settings.cittati_company,
        timeout_seconds=settings.cittati_timeout_seconds,
    ) as client:
        async with session_factory() as session:
            ingestion_run = await ingest_cittati_vehicles(session, client)
            snapshot_result = None
            if ingestion_run.status in {"succeeded", "partial"}:
                snapshot_result = await refresh_vehicle_eta_snapshots(
                    session,
                    queried_at=datetime.now(UTC),
                )
                await session.commit()

    print(
        "Cittati model 4 ingestion finished: "
        f"status={ingestion_run.status} "
        f"records={ingestion_run.records_received} "
        f"run_id={ingestion_run.id}"
    )
    if snapshot_result is not None:
        print(
            "Vehicle ETA snapshot: "
            f"performed={snapshot_result.performed} "
            f"eligible={snapshot_result.eligible_vehicle_count} "
            f"written={snapshot_result.snapshot_count} "
            f"unavailable={snapshot_result.unavailable_vehicle_count}"
        )


if __name__ == "__main__":
    asyncio.run(run())
