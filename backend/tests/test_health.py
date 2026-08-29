from unittest.mock import AsyncMock

import app.api.health as health_module
from app.main import app
from app.services.operational_health import CittatiOperationalStatus
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

client = TestClient(app)


def test_health_returns_service_status() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "GTFS On Time",
        "version": "0.1.0",
    }


def test_readiness_returns_ready_when_database_is_available(
    monkeypatch,
) -> None:
    database_check = AsyncMock()
    monkeypatch.setattr(
        health_module,
        "check_database_connection",
        database_check,
    )

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "ok",
    }
    database_check.assert_awaited_once()


def test_readiness_returns_503_when_database_is_unavailable(
    monkeypatch,
) -> None:
    database_check = AsyncMock(
        side_effect=SQLAlchemyError("database unavailable"),
    )
    monkeypatch.setattr(
        health_module,
        "check_database_connection",
        database_check,
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "status": "not_ready",
            "database": "unavailable",
        },
    }


def test_operational_health_returns_last_success(monkeypatch) -> None:
    operational_check = AsyncMock(
        return_value=CittatiOperationalStatus(
            status="operational",
            latest_attempt_status="succeeded",
            last_success_at=None,
            last_success_age_seconds=8,
        )
    )
    monkeypatch.setattr(
        health_module,
        "query_cittati_operational_status",
        operational_check,
    )

    async def fake_session() -> object:
        yield object()

    from app.db.session import get_database_session

    app.dependency_overrides[get_database_session] = fake_session
    try:
        response = client.get("/health/operational")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "operational"
    assert response.json()["last_success_age_seconds"] == 8
