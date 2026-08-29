import asyncio

from sqlalchemy import select

from app.db.session import session_factory
from app.models import GtfsFeed
from app.services.monotonic_stop_projection import reproject_gtfs_stops_monotonically


async def main() -> None:
    async with session_factory() as session:
        feed_id = await session.scalar(
            select(GtfsFeed.id).order_by(GtfsFeed.retrieved_at.desc()).limit(1)
        )
        if feed_id is None:
            raise RuntimeError("No GTFS feed is available for stop projection.")
        result = await reproject_gtfs_stops_monotonically(session, feed_id=feed_id)
        await session.commit()
    print(
        "GTFS bounded monotonic stop projection finished: "
        f"patterns={result.pattern_count} "
        f"fallback_patterns={result.fallback_pattern_count} "
        f"pattern_stops={result.assigned_stop_count} "
        f"stop_times={result.updated_stop_time_count}"
    )


if __name__ == "__main__":
    asyncio.run(main())
