from datetime import UTC, datetime
from unittest.mock import AsyncMock

import app.api.v1.prescriptions as prescriptions_module
from app.db.session import get_database_session
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


async def fake_session() -> object:
    yield object()


def test_vehicle_swap_endpoint_returns_prescriptive_snapshot(monkeypatch) -> None:
    evaluated_at = datetime(2026, 8, 30, 12, tzinfo=UTC)
    query = AsyncMock(
        return_value={
            "status": "ready",
            "evaluated_at": evaluated_at,
            "snapshot_generated_at": evaluated_at,
            "snapshot_age_seconds": 0,
            "delay_threshold_minutes": 10,
            "protected_window_minutes": 10,
            "eligible_vehicle_count": 0,
            "terminal_count": 0,
            "plan_count": 0,
            "total_saved_delay_seconds": 0,
            "plans": [],
        }
    )
    monkeypatch.setattr(
        prescriptions_module,
        "query_vehicle_swap_prescriptions",
        query,
    )
    app.dependency_overrides[get_database_session] = fake_session
    try:
        response = client.get("/api/v1/prescriptions/vehicle-swaps")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["protected_window_minutes"] == 10
    assert query.await_count == 1


def test_confirm_vehicle_swap_execution(monkeypatch) -> None:
    executed_at = datetime(2026, 8, 31, 15, tzinfo=UTC)
    execute = AsyncMock(
        return_value={
            "execution_key": "a" * 64,
            "group_id": "terminal-G01",
            "terminal_id": "terminal",
            "snapshot_generated_at": executed_at,
            "executed_at": executed_at,
            "executed_by": "Operador 1",
        }
    )
    monkeypatch.setattr(prescriptions_module, "execute_exchange_group", execute)
    app.dependency_overrides[get_database_session] = fake_session
    try:
        response = client.post(
            "/api/v1/prescriptions/vehicle-swap-executions",
            json={"execution_key": "a" * 64, "executed_by": "Operador 1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["executed_by"] == "Operador 1"
