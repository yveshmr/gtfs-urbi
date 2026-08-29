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
