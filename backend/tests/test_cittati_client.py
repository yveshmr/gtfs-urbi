import base64
import hashlib
import json
from datetime import date

import httpx
import pytest
from app.integrations.cittati import CittatiAuthenticationError, CittatiClient


@pytest.mark.asyncio
async def test_fetch_vehicles_preserves_complete_payload() -> None:
    payload = {
        "retornoOK": True,
        "veiculos": [
            {
                "prefixo": "001",
                "campoAindaNaoModelado": {
                    "valor": 42,
                    "marcadores": ["a", "b"],
                },
            }
        ],
    }
    vehicle_content = json.dumps(payload).encode()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/Autenticacao/AutenticarUsuario"):
            return httpx.Response(200, json={"retornoOK": True, "token": "session-token"})

        return httpx.Response(
            200,
            content=vehicle_content,
            headers={"Content-Type": "application/json"},
        )

    async with httpx.AsyncClient(
        base_url="https://cittati.example/WSIntegracaoCittati/",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        client = CittatiClient(
            base_url="https://ignored.example",
            username="integration-user",
            password="integration-password",
            company="company-id",
            http_client=http_client,
        )

        result = await client.fetch_vehicles()

    assert result.payload == payload
    assert result.http_status == 200
    assert result.endpoint_name == "operacional/veiculos"
    assert result.request_params == {"empresa": "company-id", "modelo": 4}
    assert result.payload_hash == hashlib.sha256(vehicle_content).hexdigest()

    authentication_request, vehicles_request = requests
    expected_basic = base64.b64encode(b"integration-user:integration-password").decode()
    assert authentication_request.method == "POST"
    assert authentication_request.headers["Authorization"] == f"Basic {expected_basic}"
    assert authentication_request.url.query == b""

    assert vehicles_request.method == "GET"
    assert vehicles_request.headers["Authorization"] == "Bearer session-token"
    assert dict(vehicles_request.url.params) == {
        "empresa": "company-id",
        "modelo": "4",
    }


@pytest.mark.asyncio
async def test_authentication_failure_does_not_request_vehicles() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(
            200,
            json={
                "retornoOK": False,
                "codigoErro": "02",
                "descricaoErro": "Token invalido",
            },
        )

    async with httpx.AsyncClient(
        base_url="https://cittati.example/WSIntegracaoCittati/",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        client = CittatiClient(
            base_url="https://ignored.example",
            username="integration-user",
            password="integration-password",
            company="company-id",
            http_client=http_client,
        )

        with pytest.raises(CittatiAuthenticationError, match=r"\(02\)"):
            await client.fetch_vehicles()

    assert request_count == 1


@pytest.mark.asyncio
async def test_fetch_trips_uses_authenticated_company_and_reuses_session() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/Autenticacao/AutenticarUsuario"):
            return httpx.Response(
                200,
                json={
                    "retornoOK": True,
                    "token": "session-token",
                    "empresas": ["authenticated-company"],
                },
            )
        return httpx.Response(200, json={"retornoOK": True, "viagens": []})

    async with httpx.AsyncClient(
        base_url="https://cittati.example/WSIntegracaoCittati/",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        client = CittatiClient(
            base_url="https://ignored.example",
            username="integration-user",
            password="integration-password",
            company="vehicle-endpoint-company",
            http_client=http_client,
        )
        await client.fetch_vehicles()
        result = await client.fetch_trips(service_date=date(2026, 8, 31))

    assert len([request for request in requests if "AutenticarUsuario" in request.url.path]) == 1
    trips_request = requests[-1]
    assert trips_request.url.path.endswith("/Operacional/ConsultarViagens")
    assert dict(trips_request.url.params) == {
        "data": "31/08/2026",
        "empresa": "authenticated-company",
    }
    assert result.endpoint_name == "Operacional/ConsultarViagens"
