from datetime import UTC, datetime
from unittest.mock import AsyncMock

import app.api.v1.map as map_module
from app.db.session import get_database_session
from app.main import app
from app.services.map_query import TripGeometryNotFoundError
from fastapi.testclient import TestClient

client = TestClient(app)


async def fake_session() -> object:
    yield object()


def test_map_vehicle_endpoint_uses_projected_position_query(monkeypatch) -> None:
    query = AsyncMock(
        return_value={
            "generated_at": datetime(2026, 8, 30, 12, tzinfo=UTC),
            "count": 0,
            "vehicles": [],
        }
    )
    monkeypatch.setattr(map_module, "query_projected_vehicle_positions", query)
    app.dependency_overrides[get_database_session] = fake_session
    try:
        response = client.get("/api/v1/map/vehicles")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["count"] == 0
    assert response.headers["cache-control"] == "no-store"
    assert query.await_count == 1


def test_trip_geometry_endpoint_returns_404(monkeypatch) -> None:
    monkeypatch.setattr(
        map_module,
        "query_trip_geometry",
        AsyncMock(side_effect=TripGeometryNotFoundError("unknown")),
    )
    app.dependency_overrides[get_database_session] = fake_session
    try:
        response = client.get("/api/v1/map/trips/unknown/geometry")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Trip geometry not found."}
