from datetime import UTC, datetime, timedelta

from app.integrations.cittati import CittatiError, CittatiRawResponse
from app.services.vehicle_schedule_context import (
    VehicleScheduleContextService,
    select_active_trip_contexts,
)

NOW = datetime(2026, 8, 31, 15, tzinfo=UTC)  # 12:00 in Sao Paulo


def cittati_time(minutes: int) -> str:
    value = NOW + timedelta(minutes=minutes)
    return value.astimezone().strftime("%d/%m/%Y %H:%M:%S")


def test_selects_real_trip_in_progress_over_planned_candidate() -> None:
    payload = {
        "viagens": [
            {
                "veiculo": "001",
                "inicioProgramado": cittati_time(-20),
                "fimProgramado": cittati_time(20),
                "nomePontoFim": "Planned candidate",
            },
            {
                "veiculo": "001",
                "inicioProgramado": cittati_time(-40),
                "inicioRealizado": cittati_time(-35),
                "fimProgramado": cittati_time(5),
                "fimRealizado": None,
                "nomePontoInicio": "Origem",
                "nomePontoFim": "Terminal",
                "codAtendimento": "ATD",
                "atividade": "OPERACAO",
                "tabela": "T01",
                "linha": "100",
                "sentido": "I",
                "tipoDia": "UTIL",
                "numeroViagem": 42,
            },
        ]
    }

    contexts = select_active_trip_contexts(payload, evaluated_at=NOW)

    assert len(contexts) == 1
    context = contexts[0]
    assert context.vehicle_prefix == "001"
    assert context.destination_name == "Terminal"
    assert context.attendance_code == "ATD"
    assert context.trip_number == "42"


def test_ignores_trip_outside_operational_window() -> None:
    payload = {
        "viagens": [
            {
                "veiculo": "001",
                "inicioProgramado": cittati_time(-120),
                "fimProgramado": cittati_time(-60),
                "fimRealizado": cittati_time(-58),
            }
        ]
    }

    assert select_active_trip_contexts(payload, evaluated_at=NOW) == []


class FlakyClient:
    def __init__(self) -> None:
        self.calls = 0

    async def fetch_trips(self, *, service_date: object) -> CittatiRawResponse:
        self.calls += 1
        if self.calls > 1:
            raise CittatiError("temporary failure")
        return CittatiRawResponse(
            endpoint_name="Operacional/ConsultarViagens",
            requested_at=NOW,
            received_at=NOW,
            duration_ms=1,
            http_status=200,
            request_params={},
            payload_hash="hash",
            payload={"viagens": []},
        )

    async def aclose(self) -> None:
        return None


async def test_returns_stale_cache_when_refresh_fails() -> None:
    service = VehicleScheduleContextService(FlakyClient())  # type: ignore[arg-type]

    ready = await service.get(evaluated_at=NOW)
    stale = await service.get(evaluated_at=NOW + timedelta(seconds=31))

    assert ready.status == "ready"
    assert stale.status == "stale"
    assert stale.cache_age_seconds == 31
