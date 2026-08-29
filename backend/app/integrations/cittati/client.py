from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

import httpx


class CittatiError(RuntimeError):
    """Base exception for Cittati integration failures."""


class CittatiAuthenticationError(CittatiError):
    """Raised when Cittati does not issue a usable session token."""


class CittatiInvalidResponseError(CittatiError):
    """Raised when Cittati returns a response that is not valid JSON."""


@dataclass(frozen=True, slots=True)
class CittatiRawResponse:
    endpoint_name: str
    requested_at: datetime
    received_at: datetime
    duration_ms: int
    http_status: int
    request_params: dict[str, str | int]
    payload_hash: str
    payload: Any


class CittatiClient:
    """Thin client that preserves Cittati payloads without business interpretation."""

    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        company: str,
        timeout_seconds: float = 30.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._username = username
        self._password = password
        self._company = company
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/",
            timeout=timeout_seconds,
        )

    async def __aenter__(self) -> CittatiClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()

    async def authenticate(self) -> str:
        response = await self._http_client.post(
            "Autenticacao/AutenticarUsuario",
            auth=httpx.BasicAuth(self._username, self._password),
        )
        response.raise_for_status()
        payload = self._decode_json(response)

        if not isinstance(payload, dict):
            raise CittatiAuthenticationError(
                "Cittati authentication response must be a JSON object."
            )

        token = payload.get("token")
        if payload.get("retornoOK") is not True or not isinstance(token, str) or not token:
            error_code = payload.get("codigoErro", "unknown")
            description = payload.get("descricaoErro", "authentication rejected")
            raise CittatiAuthenticationError(
                f"Cittati authentication failed ({error_code}): {description}"
            )

        return token

    async def fetch_vehicles(self, *, model: int = 4) -> CittatiRawResponse:
        token = await self.authenticate()
        request_params: dict[str, str | int] = {
            "empresa": self._company,
            "modelo": model,
        }
        requested_at = datetime.now(UTC)
        started_at = perf_counter()

        response = await self._http_client.get(
            "operacional/veiculos",
            params=request_params,
            headers={"Authorization": f"Bearer {token}"},
        )

        received_at = datetime.now(UTC)
        duration_ms = round((perf_counter() - started_at) * 1000)
        payload = self._decode_json(response)

        return CittatiRawResponse(
            endpoint_name="operacional/veiculos",
            requested_at=requested_at,
            received_at=received_at,
            duration_ms=duration_ms,
            http_status=response.status_code,
            request_params=request_params,
            payload_hash=hashlib.sha256(response.content).hexdigest(),
            payload=payload,
        )

    @staticmethod
    def _decode_json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as error:
            raise CittatiInvalidResponseError(
                f"Cittati returned non-JSON content with HTTP {response.status_code}."
            ) from error
