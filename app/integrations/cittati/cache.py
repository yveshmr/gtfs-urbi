from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

FMT = "%d/%m/%Y %H:%M:%S"


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.strptime(s, FMT)
    except Exception:
        return None


def escolher_viagem_ativa_por_prefixo(
    payload: Dict[str, Any],
    now: Optional[datetime] = None
) -> Dict[str, Dict[str, Any]]:
    """
    Retorna um dict {prefixo: viagem_escolhida} usando:
      - Preferência forte por viagem com inicioRealizado != None e fimRealizado == None
      - Fallback: janela do programado (inicioProgramado/fimProgramado) perto do "now"

    A viagem retornada já vem com os campos necessários para enriquecer /map/vehicles/table:
      inicioProgramado, inicioRealizado, fimProgramado,
      nomePontoInicio, nomePontoFim, codAtendimento, atividade, tabela
    """
    if now is None:
        now = datetime.now()

    viagens: List[Dict[str, Any]] = payload.get("viagens") or []

    pre = timedelta(minutes=10)
    post = timedelta(minutes=30)

    candidatos: Dict[str, List[Dict[str, Any]]] = {}

    for v in viagens:
        prefixo = (v.get("veiculo") or "").strip()
        if not prefixo:
            continue

        ip = _parse_dt(v.get("inicioProgramado"))
        ir = _parse_dt(v.get("inicioRealizado"))
        fp = _parse_dt(v.get("fimProgramado"))
        fr = _parse_dt(v.get("fimRealizado"))

        # Regra principal: em duração (real começou e ainda não terminou)
        in_progress_real = ir is not None and fr is None

        # Fallback (útil quando inicioRealizado/fimRealizado não vêm): janela do programado
        in_window_prog = False
        if ip and fp:
            in_window_prog = (ip - pre) <= now <= (fp + post)

        if in_progress_real or in_window_prog:
            candidatos.setdefault(prefixo, []).append({
                # tempos
                "inicioProgramado": v.get("inicioProgramado"),
                "inicioRealizado": v.get("inicioRealizado"),
                "fimProgramado": v.get("fimProgramado"),
                "fimRealizado": v.get("fimRealizado"),

                # campos que você quer injetar na tabela
                "nomePontoInicio": v.get("nomePontoInicio"),
                "nomePontoFim": v.get("nomePontoFim"),
                "codAtendimento": v.get("codAtendimento"),
                "atividade": v.get("atividade"),
                "tabela": v.get("tabela"),

                # (opcional) manter também caso você queira usar depois
                "linha": v.get("linha"),
                "sentido": v.get("sentido"),
                "tipoDia": v.get("tipoDia"),
                "numeroViagem": v.get("numeroViagem"),
            })

    out: Dict[str, Dict[str, Any]] = {}

    def _score(x: Dict[str, Any]) -> float:
        ir2 = _parse_dt(x.get("inicioRealizado"))
        ip2 = _parse_dt(x.get("inicioProgramado"))
        # Prioriza fortemente o que está em duração
        bonus = 1e12 if (ir2 is not None and x.get("fimRealizado") is None) else 0
        t = (ir2 or ip2)
        return bonus + (t.timestamp() if t else 0.0)

    for prefixo, lst in candidatos.items():
        lst.sort(key=_score, reverse=True)
        out[prefixo] = lst[0]

    return out