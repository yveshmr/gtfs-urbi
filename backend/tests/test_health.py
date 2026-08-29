from unittest.mock import AsyncMock

import app.api.health as health_module
from app.main import app
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
