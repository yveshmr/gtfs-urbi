import base64
import time
from typing import Optional, Dict, Any, List
import requests

AUTH_URL = "http://servicos.cittati.com.br/WSIntegracaoCittati/Autenticacao/AutenticarUsuario"
VIAGENS_URL = "http://servicos.cittati.com.br/WSIntegracaoCittati/Operacional/ConsultarViagens"


class CittatiClient:
    """
    Cliente isolado para integração com Cittati (Viagens).
    - Autentica via Basic base64(usuario:senha)
    - Recebe token Bearer e lista de empresas
    - Usa sempre a primeira empresa (idEmpresa) retornada
    """

    def __init__(self, usuario: str, senha: str, timeout: int = 20):
        self.usuario = usuario
        self.senha = senha
        self.timeout = timeout

        self._token: Optional[str] = None
        self._token_ts: float = 0.0  # epoch seconds
        self._empresas: Optional[List[str]] = None

    def _basic_header(self) -> Dict[str, str]:
        raw = f"{self.usuario}:{self.senha}".encode("utf-8")
        b64 = base64.b64encode(raw).decode("ascii")
        return {"Authorization": f"Basic {b64}"}

    def _bearer_header(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _session_valid(self) -> bool:
        # doc fala até 24h — vamos renovar antes (23h)
        return self._token is not None and (time.time() - self._token_ts) < (23 * 3600)

    def authenticate(self) -> Dict[str, Any]:
        """
        Autentica e preenche token + empresas.
        Retorna o JSON de autenticação.
        """
        resp = requests.get(AUTH_URL, headers=self._basic_header(), timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()

        if not data.get("retornoOK") or not data.get("token"):
            raise RuntimeError(f"Falha autenticação Cittati: {data}")

        empresas = data.get("empresas") or []
        if not isinstance(empresas, list) or not empresas:
            raise RuntimeError(f"Autenticação OK mas sem lista de empresas: {data}")

        self._token = data["token"]
        self._token_ts = time.time()
        self._empresas = empresas
        return data

    def get_token(self) -> str:
        if self._session_valid():
            return self._token  # type: ignore
        self.authenticate()
        return self._token  # type: ignore

    def get_empresa_default(self) -> str:
        if self._empresas and len(self._empresas) > 0:
            return self._empresas[0]
        # se não tiver em memória, autentica e pega
        self.authenticate()
        return self._empresas[0]  # type: ignore

    def consultar_viagens(
        self,
        data_ddmmyyyy: str,
        numerolinha: Optional[str] = None,
        prefixoVeiculo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Consulta viagens da data para a empresa default (primeiro idEmpresa).
        """
        token = self.get_token()
        empresa = self.get_empresa_default()

        params: Dict[str, Any] = {"data": data_ddmmyyyy, "empresa": empresa}
        if numerolinha:
            params["numerolinha"] = numerolinha
        if prefixoVeiculo:
            params["prefixoVeiculo"] = prefixoVeiculo

        resp = requests.get(
            VIAGENS_URL,
            params=params,
            headers=self._bearer_header(token),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()