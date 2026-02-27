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


def escolher_viagem_ativa_por_prefixo(payload: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Dict[str, Any]]:
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

        in_progress_real = ir is not None and fr is None

        in_window_prog = False
        if ip and fp:
            in_window_prog = (ip - pre) <= now <= (fp + post)

        if in_progress_real or in_window_prog:
            candidatos.setdefault(prefixo, []).append({
                "inicioProgramado": v.get("inicioProgramado"),
                "inicioRealizado": v.get("inicioRealizado"),
                "fimProgramado": v.get("fimProgramado"),
                "fimRealizado": v.get("fimRealizado"),
                "linha": v.get("linha"),
                "sentido": v.get("sentido"),
                "tabela": v.get("tabela"),
                "tipoDia": v.get("tipoDia"),
                "numeroViagem": v.get("numeroViagem"),
            })

    out: Dict[str, Dict[str, Any]] = {}

    def _score(x: Dict[str, Any]) -> float:
        ir = _parse_dt(x.get("inicioRealizado"))
        ip = _parse_dt(x.get("inicioProgramado"))
        bonus = 1e12 if (ir is not None and x.get("fimRealizado") is None) else 0
        t = (ir or ip)
        return bonus + (t.timestamp() if t else 0.0)

    for prefixo, lst in candidatos.items():
        lst.sort(key=_score, reverse=True)
        out[prefixo] = lst[0]

    return out