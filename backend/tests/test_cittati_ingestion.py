import uuid
from datetime import UTC, datetime

import pytest
from app.integrations.cittati import CittatiRawResponse
from app.models import IngestionRun
from app.services.active_trip_index import ActiveTripCandidate, ActiveTripIndex
from app.services.cittati_ingestion import (
    apply_exact_trip_correlations,
    ingest_cittati_vehicles,
    parse_vehicle_batch,
)
from app.services.trip_correlation import TripCorrelationKey


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commit_count = 0
        self.executed: list[object] = []

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        for instance in self.added:
            if isinstance(instance, IngestionRun) and instance.id is None:
                instance.id = uuid.uuid4()

    async def commit(self) -> None:
        self.commit_count += 1

    async def execute(self, statement: object, parameters: object = None) -> "FakeResult":
        self.executed.append((statement, parameters))
        return FakeResult()


class FakeResult:
    def mappings(self) -> list[dict[str, object]]:
        return []


class FakeVehicleSource:
    def __init__(self, response: CittatiRawResponse) -> None:
        self.response = response
        self.requested_models: list[int] = []

    async def fetch_vehicles(self, *, model: int = 4) -> CittatiRawResponse:
        self.requested_models.append(model)
        return self.response


EMPTY_TRIP_INDEX = ActiveTripIndex(candidates_by_key={}, candidates_by_trip_id={})


def make_response(payload: object, *, http_status: int = 200) -> CittatiRawResponse:
    now = datetime.now(UTC)
    return CittatiRawResponse(
        endpoint_name="operacional/veiculos",
        requested_at=now,
        received_at=now,
        duration_ms=25,
        http_status=http_status,
        request_params={"empresa": "company-id", "modelo": 4},
        payload_hash="a" * 64,
        payload=payload,
    )


@pytest.mark.asyncio
async def test_ingestion_upserts_current_state_without_preserving_raw_response() -> None:
    payload = {
        "campos": [
            "Prefixo",
            "DataHora",
            "GPS_Latitude",
            "GPS_Longitude",
            "Linha_atual",
            "Velocidade",
            "campo_desconhecido",
        ],
        "dados": [
            [
                "001",
                "28/08/2026 10:00:00",
                "-15,75",
                "-47,90",
                "0.038",
                "25,5",
                {"nested": [1, 2, 3]},
            ],
            ["002", None, None, None, None, None, None],
        ],
    }
    session = FakeSession()
    source = FakeVehicleSource(make_response(payload))

    run = await ingest_cittati_vehicles(  # type: ignore[arg-type]
        session,
        source,
        active_trip_index=EMPTY_TRIP_INDEX,
    )

    assert source.requested_models == [4]
    assert run.status == "succeeded"
    assert run.records_received == 2
    assert run.records_written == 2
    assert session.commit_count == 1
    assert len(session.executed) == 9
    assert "5 minutes" in str(session.executed[0][0])
    assert all(isinstance(item, IngestionRun) for item in session.added)
    assert run.run_metadata["storage_mode"] == "current_state_only"
    assert run.run_metadata["invalid_locations"] == 1


@pytest.mark.asyncio
async def test_unexpected_payload_is_not_preserved_and_marks_run_failed() -> None:
    payload = {
        "retornoOK": False,
        "codigoErro": "02",
        "descricaoErro": "Token invalido",
    }
    session = FakeSession()
    source = FakeVehicleSource(make_response(payload))

    run = await ingest_cittati_vehicles(  # type: ignore[arg-type]
        session,
        source,
        active_trip_index=EMPTY_TRIP_INDEX,
    )

    assert run.status == "failed"
    assert run.records_received == 0
    assert run.records_written == 0
    assert session.executed == []
    assert all(isinstance(item, IngestionRun) for item in session.added)


@pytest.mark.asyncio
async def test_transport_failure_is_audited_and_reraised() -> None:
    class FailingSource:
        async def fetch_vehicles(self, *, model: int = 4) -> CittatiRawResponse:
            raise RuntimeError("upstream unavailable")

    session = FakeSession()

    with pytest.raises(RuntimeError, match="upstream unavailable"):
        await ingest_cittati_vehicles(  # type: ignore[arg-type]
            session,
            FailingSource(),
        )

    run = next(item for item in session.added if isinstance(item, IngestionRun))
    assert run.status == "failed"
    assert run.finished_at is not None
    assert session.commit_count == 1


def test_parse_vehicle_batch_preserves_all_fields_in_overwritten_state() -> None:
    received_at = datetime.now(UTC)
    run_id = uuid.uuid4()
    payload = {
        "campos": [
            "Prefixo",
            "DataHora",
            "GPS_Latitude",
            "GPS_Longitude",
            "Linha_atual",
            "campo_futuro",
        ],
        "dados": [
            [
                "001",
                "28/08/2026 10:00:00",
                "-15.75",
                "-47.90",
                "0.038",
                {"nested": [1, 2, 3]},
            ]
        ],
    }

    batch = parse_vehicle_batch(
        payload,
        ingestion_run_id=run_id,
        payload_hash="b" * 64,
        received_at=received_at,
    )

    assert batch.rejected_count == 0
    assert batch.invalid_location_count == 0
    assert len(batch.rows) == 1
    row = batch.rows[0]
    assert row["vehicle_prefix"] == "001"
    assert row["normalized_current_line"] == "0038"
    assert row["source_timestamp"] == datetime(2026, 8, 28, 13, 0, tzinfo=UTC)
    assert row["source_data"]["campo_futuro"] == {"nested": [1, 2, 3]}


def test_parse_vehicle_batch_rejects_rows_without_a_stable_prefix() -> None:
    batch = parse_vehicle_batch(
        {"campos": ["Prefixo", "DataHora"], "dados": [[None, "invalid"]]},
        ingestion_run_id=uuid.uuid4(),
        payload_hash="c" * 64,
        received_at=datetime.now(UTC),
    )

    assert batch.rows == []
    assert batch.rejected_count == 1


def test_parse_vehicle_batch_starts_low_speed_timer_on_first_observation() -> None:
    received_at = datetime(2026, 8, 28, 13, 1, tzinfo=UTC)
    batch = parse_vehicle_batch(
        {
            "campos": ["Prefixo", "DataHora", "Velocidade"],
            "dados": [["001", "28/08/2026 10:00:00", "0,5"]],
        },
        ingestion_run_id=uuid.uuid4(),
        payload_hash="e" * 64,
        received_at=received_at,
    )

    assert batch.rows[0]["low_speed_since"] == datetime(2026, 8, 28, 13, 0, tzinfo=UTC)


def test_exact_trip_match_enriches_current_state_for_projection() -> None:
    feed_id = uuid.uuid4()
    batch = parse_vehicle_batch(
        {
            "campos": [
                "Prefixo",
                "Linha_atual",
                "GTFS_Sentido_atual",
                "HoraViagemPlanejada_atual",
            ],
            "dados": [["001", "0.038", "1", "10:30"]],
        },
        ingestion_run_id=uuid.uuid4(),
        payload_hash="d" * 64,
        received_at=datetime.now(UTC),
    )
    index = ActiveTripIndex(
        candidates_by_key={
            TripCorrelationKey("0038", "1", "10:30:00"): ("trip-1",),
        },
        candidates_by_trip_id={
            "trip-1": ActiveTripCandidate(feed_id, "trip-1", "route-1", "shape-1"),
        },
    )

    apply_exact_trip_correlations(batch.rows, index)

    row = batch.rows[0]
    assert row["correlation_status"] == "matched"
    assert row["correlation_reason"] == "unique_exact_match"
    assert row["correlation_level"] == 1
    assert row["feed_id"] == feed_id
    assert row["trip_id"] == "trip-1"
    assert row["route_id"] == "route-1"
    assert row["shape_id"] == "shape-1"
