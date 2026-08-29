import asyncio

from app.core.config import get_settings
from app.db.session import session_factory
from app.integrations.gtfs_static import GtfsStaticClient
from app.services.gtfs_static_ingestion import ingest_gtfs_static


async def run() -> None:
    settings = get_settings()
    async with GtfsStaticClient(
        source_url=settings.gtfs_static_url,
        timeout_seconds=settings.gtfs_static_timeout_seconds,
    ) as client:
        async with session_factory() as session:
            ingestion_run = await ingest_gtfs_static(session, client)

    print(
        "GTFS static ingestion finished: "
        f"status={ingestion_run.status} "
        f"records={ingestion_run.records_received} "
        f"run_id={ingestion_run.id}"
    )


if __name__ == "__main__":
    asyncio.run(run())
