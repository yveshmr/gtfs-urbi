from datetime import UTC, datetime
from unittest.mock import AsyncMock

import app.api.v1.segments as segments_module
from app.db.session import get_database_session
from app.main import app
from app.services.segment_aggregation import ResolvedSegmentEstimate
from app.services.segment_estimate_query import SegmentEstimatePair
from fastapi.testclient import TestClient

client = TestClient(app)


async def fake_session() -> object:
    yield object()


def test_segment_estimate_exposes_physical_and_service_in_parallel(
    monkeypatch,
) -> None:
    query = AsyncMock(
        return_value=SegmentEstimatePair(
            physical=ResolvedSegmentEstimate(100, 0.6, 3, "live", 20, None),
            service=ResolvedSegmentEstimate(110, 0.4, 2, "historical", None, -5),
        )
    )
    monkeypatch.setattr(segments_module, "query_segment_estimates", query)
    app.dependency_overrides[get_database_session] = fake_session
    try:
        response = client.get(
            "/api/v1/segments/estimate",
            params={
                "origin_stop_id": "A",
                "destination_stop_id": "B",
                "route_id": "R1",
                "direction_id": 1,
                "queried_at": datetime(2026, 8, 29, 13, tzinfo=UTC).isoformat(),
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["physical"]["source"] == "live"
    assert body["physical"]["value_seconds"] == 100
    assert body["service"]["source"] == "historical"
    assert body["service"]["historical_offset_minutes"] == -5


def test_segment_estimate_requires_route_and_direction_together() -> None:
    app.dependency_overrides[get_database_session] = fake_session
    try:
        response = client.get(
            "/api/v1/segments/estimate",
            params={
                "origin_stop_id": "A",
                "destination_stop_id": "B",
                "route_id": "R1",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["detail"] == "Route and direction must be provided together."
