from datetime import UTC, datetime
from unittest.mock import AsyncMock

import app.api.v1.vehicles as vehicles_module
from app.db.session import get_database_session
from app.main import app
from app.services.vehicle_eta_query import VehicleNotFoundError
from fastapi.testclient import TestClient

client = TestClient(app)


async def fake_session() -> object:
    yield object()


def test_vehicle_eta_returns_404_for_unknown_vehicle(monkeypatch) -> None:
    monkeypatch.setattr(
        vehicles_module,
        "query_vehicle_eta",
        AsyncMock(side_effect=VehicleNotFoundError("unknown")),
    )
    app.dependency_overrides[get_database_session] = fake_session
    try:
        response = client.get("/api/v1/vehicles/unknown/eta")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Vehicle not found."}


def test_vehicle_eta_snapshot_list_uses_materialized_fleet_view(monkeypatch) -> None:
    monkeypatch.setattr(
        vehicles_module,
        "query_vehicle_eta_snapshots",
        AsyncMock(
            return_value={
                "generated_at": None,
                "count": 0,
                "vehicles": [],
            }
        ),
    )
    app.dependency_overrides[get_database_session] = fake_session
    try:
        response = client.get("/api/v1/vehicles/eta-snapshots")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "generated_at": None,
        "count": 0,
        "vehicles": [],
    }


def test_schedule_contexts_exposes_normalized_active_trips(monkeypatch) -> None:
    service = AsyncMock()
    service.get.return_value = {
        "status": "ready",
        "generated_at": datetime(2026, 8, 31, 15, tzinfo=UTC),
        "cache_age_seconds": 0,
        "count": 1,
        "vehicles": [
            {
                "vehicle_prefix": "001",
                "planned_start_at": datetime(2026, 8, 31, 14, tzinfo=UTC),
                "actual_start_at": None,
                "planned_end_at": datetime(2026, 8, 31, 15, tzinfo=UTC),
                "actual_end_at": None,
                "origin_name": "Origem",
                "destination_name": "Terminal",
                "attendance_code": "ATD",
                "activity": "OPERACAO",
                "schedule_table": "T01",
                "line": "100",
                "direction": "I",
                "day_type": "UTIL",
                "trip_number": "42",
            }
        ],
    }
    monkeypatch.setattr(vehicles_module, "get_vehicle_schedule_context_service", lambda: service)

    response = client.get("/api/v1/vehicles/schedule-contexts")

    assert response.status_code == 200
    assert response.json()["vehicles"][0]["destination_name"] == "Terminal"
