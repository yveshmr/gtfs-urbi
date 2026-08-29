import asyncio

from app.core.config import get_settings
from app.db.session import session_factory
from app.integrations.cittati import CittatiClient
from app.services.cittati_cycle import run_cittati_cycle


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
            cycle = await run_cittati_cycle(session, client)

    print(
        "Cittati model 4 ingestion finished: "
        f"status={cycle.ingestion_run.status} "
        f"records={cycle.ingestion_run.records_received} "
        f"run_id={cycle.ingestion_run.id}"
    )
    if cycle.snapshot is not None:
        print(
            "Vehicle ETA snapshot: "
            f"performed={cycle.snapshot.performed} "
            f"eligible={cycle.snapshot.eligible_vehicle_count} "
            f"written={cycle.snapshot.snapshot_count} "
            f"unavailable={cycle.snapshot.unavailable_vehicle_count}"
        )


if __name__ == "__main__":
    asyncio.run(run())
