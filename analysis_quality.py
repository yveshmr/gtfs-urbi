import csv
import json
import math
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime

PATH = r"C:\Users\yves.ribeiro\Downloads\entregas.csv"


def blank(v):
    return v is None or not str(v).strip()


def norm_text(v):
    s = unicodedata.normalize("NFKD", (v or "").strip())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).casefold()


def num(v):
    s = (v or "").strip().replace(" ", "")
    if not s:
        return None
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    elif "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def dt(v):
    s = (v or "").strip()
    for f in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, f)
        except ValueError:
            pass
    return None


with open(PATH, "r", encoding="utf-8-sig", newline="") as f:
    rows = list(csv.DictReader(f, delimiter=";"))

cols = list(rows[0])
n = len(rows)

missing = {c: sum(blank(r[c]) for r in rows) for c in cols}
branches = sorted(set(r["filial"].strip() for r in rows if not blank(r["filial"])))
branch_missing = {}
for b in branches:
    br = [r for r in rows if r["filial"].strip() == b]
    branch_missing[b] = {
        "n": len(br),
        "blank_pct_all": round(100 * sum(blank(r[c]) for r in br for c in cols) / (len(br) * len(cols)), 3),
        "worst": sorted(
            ((c, round(100 * sum(blank(r[c]) for r in br) / len(br), 2)) for c in cols),
            key=lambda x: (-x[1], x[0]),
        )[:6],
    }

raw_tuples = [tuple(r[c] for c in cols) for r in rows]
exact_dup_rows = n - len(set(raw_tuples))
id_counts = Counter(r["id_viagem"].strip() for r in rows if not blank(r["id_viagem"]))
dup_ids = {k: v for k, v in id_counts.items() if v > 1}

normalized_tuples = [tuple(norm_text(r[c]) for c in cols) for r in rows]
normalized_dups = n - len(set(normalized_tuples))

# Near-duplicate business signature excluding trip ID and fields commonly affected by formatting.
sig_cols = ["data_coleta", "filial", "origem", "destino", "id_veiculo", "id_motorista", "cliente_id", "saida_prevista"]
sigs = Counter(tuple(norm_text(r[c]) for c in sig_cols) for r in rows)
near_groups = [v for v in sigs.values() if v > 1]
near_dup_excess = sum(v - 1 for v in near_groups)

cat_cols = ["filial", "origem", "destino", "tipo_veiculo", "segmento_cliente", "ocorrencia", "motivo_atraso", "origem_registo"]
variants = {}
for c in cat_cols:
    groups = defaultdict(Counter)
    for r in rows:
        if not blank(r[c]):
            groups[norm_text(r[c])][r[c]] += 1
    variants[c] = [dict(vals) for vals in groups.values() if len(vals) > 1]

date_formats = Counter()
for r in rows:
    s = r["data_coleta"].strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s): date_formats["ISO yyyy-mm-dd"] += 1
    elif re.fullmatch(r"\d{2}/\d{2}/\d{4}", s): date_formats["dd/mm/yyyy"] += 1
    elif s: date_formats["outro"] += 1

numeric_nonnegative = ["rota_km", "peso_kg", "volume_m3", "valor_frete_brl", "custo_combustivel_brl", "pedagio_brl", "janela_entrega_h", "chuva_mm"]
invalid = Counter()
for r in rows:
    for c in numeric_nonnegative:
        if not blank(r[c]):
            x = num(r[c])
            if x is None: invalid[c + ":nao_numerico"] += 1
            elif x < 0: invalid[c + ":negativo"] += 1
    if not blank(r["entregue_no_prazo"]) and r["entregue_no_prazo"].strip() not in {"0", "1"}:
        invalid["entregue_no_prazo:fora_0_1"] += 1
    for c in ["data_coleta", "saida_prevista", "saida_real", "chegada_prevista", "chegada_real"]:
        if not blank(r[c]) and dt(r[c]) is None:
            invalid[c + ":data_invalida"] += 1

temporal = Counter()
flag_mismatch = 0
calc_delay_mismatch = 0
collection_to_departure_hours = []
for r in rows:
    sp, sr, cp, cr, dc = (dt(r[x]) for x in ["saida_prevista", "saida_real", "chegada_prevista", "chegada_real", "data_coleta"])
    if sp and cp and cp < sp: temporal["chegada_prevista_antes_saida_prevista"] += 1
    if sr and cr and cr < sr: temporal["chegada_real_antes_saida_real"] += 1
    if dc and sr:
        collection_to_departure_hours.append((sr-dc).total_seconds()/3600)
        if sr.date() < dc.date(): temporal["saida_real_antes_data_coleta"] += 1
    delay = num(r["atraso_min"])
    ontime = num(r["entregue_no_prazo"])
    if delay is not None and ontime is not None and ((delay <= 0) != (ontime == 1)):
        flag_mismatch += 1
    if delay is not None and cp and cr:
        calc = round((cr-cp).total_seconds()/60)
        if abs(calc-delay) > 1:
            calc_delay_mismatch += 1

# Plausibility indicators based on broad physical/business bounds and robust route comparisons.
implausible = Counter()
od_dist = defaultdict(list)
for r in rows:
    x = num(r["rota_km"])
    if x is not None: od_dist[(norm_text(r["origem"]), norm_text(r["destino"]))].append(x)
od_median = {k: statistics.median(v) for k, v in od_dist.items() if len(v) >= 5}
for r in rows:
    km, peso, vol, frete, fuel, toll, temp = (num(r[x]) for x in ["rota_km","peso_kg","volume_m3","valor_frete_brl","custo_combustivel_brl","pedagio_brl","temperatura_carga_c"])
    if km is not None and (km == 0 or km > 5000): implausible["rota_km_extrema"] += 1
    med = od_median.get((norm_text(r["origem"]), norm_text(r["destino"])))
    if km is not None and med and med > 0 and (km < med/4 or km > med*4): implausible["rota_km_desvio_OD_4x"] += 1
    if peso is not None and peso > 80000: implausible["peso_acima_80t"] += 1
    if vol is not None and vol > 200: implausible["volume_acima_200m3"] += 1
    if km and fuel is not None and fuel > max(20000, km*10): implausible["combustivel_muito_alto"] += 1
    if frete is not None and frete > 100000: implausible["frete_acima_100mil"] += 1
    if toll is not None and toll > 10000: implausible["pedagio_acima_10mil"] += 1
    if temp is not None and (temp < -40 or temp > 60): implausible["temperatura_fora_-40_60"] += 1

origins = Counter((r["origem_registo"].strip() or "<vazio>") for r in rows)
origin_quality = {}
for o, count in origins.items():
    subset = [r for r in rows if (r["origem_registo"].strip() or "<vazio>") == o]
    origin_quality[o] = {
        "n": count,
        "share_pct": round(100*count/n, 2),
        "blank_pct_all": round(100*sum(blank(r[c]) for r in subset for c in cols)/(count*len(cols)), 3),
        "mixed_date_iso_pct": round(100*sum(bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["data_coleta"].strip())) for r in subset)/count, 2),
    }

result = {
    "rows": n,
    "columns": len(cols),
    "date_min": min(dt(r["data_coleta"]) for r in rows if dt(r["data_coleta"])).date().isoformat(),
    "date_max": max(dt(r["data_coleta"]) for r in rows if dt(r["data_coleta"])).date().isoformat(),
    "missing": {c: {"n": v, "pct": round(100*v/n, 3)} for c,v in sorted(missing.items(), key=lambda x:-x[1])},
    "overall_blank_pct": round(100*sum(missing.values())/(n*len(cols)), 3),
    "branch_missing": branch_missing,
    "exact_duplicate_rows": exact_dup_rows,
    "duplicate_id_excess": sum(v-1 for v in dup_ids.values()),
    "duplicate_id_groups": len(dup_ids),
    "normalized_duplicate_excess": normalized_dups,
    "near_duplicate_excess": near_dup_excess,
    "near_duplicate_groups": len(near_groups),
    "variants": variants,
    "date_formats": date_formats,
    "invalid": invalid,
    "temporal": temporal,
    "flag_mismatch": flag_mismatch,
    "calc_delay_mismatch": calc_delay_mismatch,
    "collection_to_departure_hours": {
        "median": round(statistics.median(collection_to_departure_hours),2),
        "p95": round(sorted(collection_to_departure_hours)[math.ceil(.95*len(collection_to_departure_hours))-1],2),
        "negative": sum(x < 0 for x in collection_to_departure_hours),
    },
    "implausible": implausible,
    "origins": origin_quality,
}

# Additional diagnostics for conditional fields and inferred business rules.
late_rows = [r for r in rows if num(r["atraso_min"]) is not None and num(r["atraso_min"]) > 0]
not_on_time_rows = [r for r in rows if num(r["entregue_no_prazo"]) == 0]
temp_by_segment = {}
for seg in sorted(set(r["segmento_cliente"].strip() for r in rows)):
    ss = [r for r in rows if r["segmento_cliente"].strip() == seg]
    temp_by_segment[seg] = {"n": len(ss), "temperature_filled_pct": round(100*sum(not blank(r["temperatura_carga_c"]) for r in ss)/len(ss),2)}
result["conditional_completeness"] = {
    "late_rows": len(late_rows),
    "motivo_blank_when_delay_positive_pct": round(100*sum(blank(r["motivo_atraso"]) for r in late_rows)/len(late_rows),2),
    "not_on_time_rows": len(not_on_time_rows),
    "motivo_blank_when_flag_zero_pct": round(100*sum(blank(r["motivo_atraso"]) for r in not_on_time_rows)/len(not_on_time_rows),2),
    "temperature_by_segment": temp_by_segment,
}
result["on_time_rule_mismatches"] = {
    str(t): sum(1 for r in rows if num(r["atraso_min"]) is not None and ((num(r["atraso_min"]) <= t) != (num(r["entregue_no_prazo"]) == 1)))
    for t in [0, 5, 10, 15, 30, 60]
}
result["variant_noncanonical_records"] = {
    c: sum(sum(v.values())-max(v.values()) for v in variants[c]) for c in variants
}
result["numeric_samples"] = {
    c: {
        "min": min(num(r[c]) for r in rows if num(r[c]) is not None),
        "median": statistics.median(num(r[c]) for r in rows if num(r[c]) is not None),
        "max": max(num(r[c]) for r in rows if num(r[c]) is not None),
    } for c in ["rota_km","peso_kg","volume_m3","valor_frete_brl","custo_combustivel_brl","pedagio_brl","atraso_min","temperatura_carga_c"]
}
result["origin_by_branch"] = {
    b: dict(Counter(r["origem_registo"].strip() for r in rows if r["filial"].strip() == b))
    for b in branches
}
print(json.dumps(result, ensure_ascii=False, indent=2, default=lambda x: dict(x)))
