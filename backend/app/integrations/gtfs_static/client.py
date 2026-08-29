from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import perf_counter

import httpx


@dataclass(frozen=True, slots=True)
class GtfsStaticDownload:
    source_url: str
    requested_at: datetime
    received_at: datetime
    duration_ms: int
    http_status: int
    content_hash: str
    source_last_modified: datetime | None
    content: bytes


class GtfsStaticClient:
    def __init__(
        self,
        *,
        source_url: str,
        timeout_seconds: float = 60.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._source_url = source_url
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(timeout=timeout_seconds)

    async def __aenter__(self) -> GtfsStaticClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()

    async def download(self) -> GtfsStaticDownload:
        requested_at = datetime.now(UTC)
        started_at = perf_counter()
        response = await self._http_client.get(self._source_url)
        received_at = datetime.now(UTC)
        response.raise_for_status()

        last_modified = response.headers.get("Last-Modified")
        parsed_last_modified = (
            parsedate_to_datetime(last_modified) if last_modified is not None else None
        )

        return GtfsStaticDownload(
            source_url=self._source_url,
            requested_at=requested_at,
            received_at=received_at,
            duration_ms=round((perf_counter() - started_at) * 1000),
            http_status=response.status_code,
            content_hash=hashlib.sha256(response.content).hexdigest(),
            source_last_modified=parsed_last_modified,
            content=response.content,
        )
