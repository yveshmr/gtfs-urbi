from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from typing import Any, Literal
from zoneinfo import ZoneInfo

import httpx

from app.core.config import get_settings
from app.integrations.cittati import CittatiClient, CittatiError
from app.schemas.vehicle_schedule import (
    VehicleScheduleContextListResponse,
    VehicleScheduleContextResponse,
)

_OPERATIONAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
_CACHE_TTL = timedelta(seconds=30)
_PLANNED_WINDOW_BEFORE = timedelta(minutes=10)
_PLANNED_WINDOW_AFTER = timedelta(minutes=30)
_CITTATI_DATETIME_FORMAT = "%d/%m/%Y %H:%M:%S"


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.strptime(value.strip(), _CITTATI_DATETIME_FORMAT)
    except ValueError:
        return None
    return parsed.replace(tzinfo=_OPERATIONAL_TIMEZONE).astimezone(UTC)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def select_active_trip_contexts(
    payload: Any,
    *,
    evaluated_at: datetime,
) -> list[VehicleScheduleContextResponse]:
    """Select one active or operationally-near trip per canonical vehicle prefix."""
    if evaluated_at.tzinfo is None:
        raise ValueError("The schedule evaluation timestamp must include a timezone.")
    if not isinstance(payload, dict) or not isinstance(payload.get("viagens"), list):
        return []

    candidates: dict[str, list[tuple[bool, datetime, dict[str, Any]]]] = {}
    for raw_trip in payload["viagens"]:
        if not isinstance(raw_trip, dict):
            continue
        vehicle_prefix = _optional_text(raw_trip.get("veiculo"))
        if vehicle_prefix is None:
            continue
        planned_start = _parse_datetime(raw_trip.get("inicioProgramado"))
        actual_start = _parse_datetime(raw_trip.get("inicioRealizado"))
        planned_end = _parse_datetime(raw_trip.get("fimProgramado"))
        actual_end = _parse_datetime(raw_trip.get("fimRealizado"))
        in_progress = actual_start is not None and actual_end is None
        in_planned_window = (
            planned_start is not None
            and planned_end is not None
            and planned_start - _PLANNED_WINDOW_BEFORE
            <= evaluated_at
            <= planned_end + _PLANNED_WINDOW_AFTER
        )
        if not in_progress and not in_planned_window:
            continue
        sort_at = actual_start or planned_start or datetime.min.replace(tzinfo=UTC)
        candidates.setdefault(vehicle_prefix, []).append((in_progress, sort_at, raw_trip))

    selected: list[VehicleScheduleContextResponse] = []
    for vehicle_prefix in sorted(candidates):
        _, _, raw_trip = max(candidates[vehicle_prefix], key=lambda item: (item[0], item[1]))
        selected.append(
            VehicleScheduleContextResponse(
                vehicle_prefix=vehicle_prefix,
                planned_start_at=_parse_datetime(raw_trip.get("inicioProgramado")),
                actual_start_at=_parse_datetime(raw_trip.get("inicioRealizado")),
                planned_end_at=_parse_datetime(raw_trip.get("fimProgramado")),
                actual_end_at=_parse_datetime(raw_trip.get("fimRealizado")),
                origin_name=_optional_text(raw_trip.get("nomePontoInicio")),
                destination_name=_optional_text(raw_trip.get("nomePontoFim")),
                attendance_code=_optional_text(raw_trip.get("codAtendimento")),
                activity=_optional_text(raw_trip.get("atividade")),
                schedule_table=_optional_text(raw_trip.get("tabela")),
                line=_optional_text(raw_trip.get("linha")),
                direction=_optional_text(raw_trip.get("sentido")),
                day_type=_optional_text(raw_trip.get("tipoDia")),
                trip_number=_optional_text(raw_trip.get("numeroViagem")),
            )
        )
    return selected


class VehicleScheduleContextService:
    def __init__(self, client: CittatiClient) -> None:
        self._client = client
        self._lock = asyncio.Lock()
        self._cached_at: datetime | None = None
        self._cached_service_date: date | None = None
        self._cached_response: VehicleScheduleContextListResponse | None = None

    async def get(self, *, evaluated_at: datetime) -> VehicleScheduleContextListResponse:
        evaluated_at = evaluated_at.astimezone(UTC)
        service_date = evaluated_at.astimezone(_OPERATIONAL_TIMEZONE).date()
        if self._cache_is_valid(evaluated_at, service_date):
            return self._response_with_age(evaluated_at, status="ready")
        async with self._lock:
            if self._cache_is_valid(evaluated_at, service_date):
                return self._response_with_age(evaluated_at, status="ready")
            try:
                raw = await self._client.fetch_trips(service_date=service_date)
            except (CittatiError, httpx.HTTPError):
                if self._cached_response is not None and self._cached_service_date == service_date:
                    return self._response_with_age(evaluated_at, status="stale")
                raise
            vehicles = select_active_trip_contexts(raw.payload, evaluated_at=evaluated_at)
            response = VehicleScheduleContextListResponse(
                status="ready",
                generated_at=raw.received_at,
                cache_age_seconds=0,
                count=len(vehicles),
                vehicles=vehicles,
            )
            self._cached_at = evaluated_at
            self._cached_service_date = service_date
            self._cached_response = response
            return response

    def _response_with_age(
        self,
        evaluated_at: datetime,
        *,
        status: Literal["ready", "stale"],
    ) -> VehicleScheduleContextListResponse:
        if self._cached_response is None:
            raise RuntimeError("Cittati schedule cache is not available.")
        age = max(0.0, (evaluated_at - self._cached_response.generated_at).total_seconds())
        return self._cached_response.model_copy(
            update={"status": status, "cache_age_seconds": age}
        )

    def _cache_is_valid(self, evaluated_at: datetime, service_date: date) -> bool:
        return (
            self._cached_response is not None
            and self._cached_at is not None
            and self._cached_service_date == service_date
            and evaluated_at - self._cached_at < _CACHE_TTL
        )

    async def aclose(self) -> None:
        await self._client.aclose()


@lru_cache
def get_vehicle_schedule_context_service() -> VehicleScheduleContextService:
    settings = get_settings()
    if not settings.cittati_username or settings.cittati_password is None:
        raise RuntimeError("Cittati credentials are not configured.")
    return VehicleScheduleContextService(
        CittatiClient(
            base_url=settings.cittati_base_url,
            username=settings.cittati_username,
            password=settings.cittati_password.get_secret_value(),
            company=settings.cittati_company or settings.cittati_username,
            timeout_seconds=settings.cittati_timeout_seconds,
        )
    )
