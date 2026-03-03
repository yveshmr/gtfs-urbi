import { useEffect, useMemo, useState } from "react";
import logo from "./assets/logo.png";

// =========================
// FORMATADORES / PARSERS
// =========================

function pad2(n) {
  return String(n).padStart(2, "0");
}

// aceita ISO, "dd/mm/yyyy HH:MM:SS" (Cittati) ou null
function parseDateFlex(value) {
  if (!value) return null;

  if (value instanceof Date && !isNaN(value.getTime())) return value;

  // timestamp (ms) ou (s)
  if (typeof value === "number") {
    const ms = value > 2_000_000_000 ? value : value * 1000;
    const d = new Date(ms);
    return isNaN(d.getTime()) ? null : d;
  }

  const s0 = String(value).trim();
  if (!s0) return null;

  // ✅ FIX: alguns ISOs vêm com microssegundos (ex: ...41.699904), e o Date do JS pode falhar.
  // Convertemos para milissegundos (3 dígitos) antes de tentar parsear.
  const s = s0.replace(/(\.\d{3})\d+/, "$1");

  // ISO
  const isoTry = new Date(s);
  if (!isNaN(isoTry.getTime())) return isoTry;

  // Cittati: "27/02/2026 07:33:39"
  const m = s.match(/^(\d{2})\/(\d{2})\/(\d{4})\s+(\d{2}):(\d{2})(?::(\d{2}))?$/);
  if (m) {
    const dd = Number(m[1]);
    const mm = Number(m[2]);
    const yyyy = Number(m[3]);
    const HH = Number(m[4]);
    const MM = Number(m[5]);
    const SS = Number(m[6] ?? 0);
    const d = new Date(yyyy, mm - 1, dd, HH, MM, SS);
    return isNaN(d.getTime()) ? null : d;
  }

  return null;
}

function fmtHHMM(value) {
  const d = parseDateFlex(value);
  if (!d) return "—";
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

function fmtHHMMSS(value) {
  const d = parseDateFlex(value);
  if (!d) return "—";
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
}

function statusStyle(status) {
  const base = {
    display: "inline-block",
    padding: "4px 10px",
    borderRadius: 999,
    fontSize: 12,
    fontWeight: 700,
    color: "white",
    lineHeight: "12px",
    textTransform: "uppercase",
    letterSpacing: "0.3px",
    whiteSpace: "nowrap",
  };

  if (status === "on_time") return { ...base, background: "#00aa00" };
  if (status === "delayed") return { ...base, background: "#ff8800" };
  if (status === "early") return { ...base, background: "#6a5acd" };
  return { ...base, background: "#999999" };
}

function formatDelay(minutes) {
  if (minutes == null) return "—";
  if (minutes === 0) return "no horário";
  if (minutes > 0) return `+${minutes} min`;
  return `${minutes} min`;
}

function diffMinutes(a, b) {
  const da = parseDateFlex(a);
  const db = parseDateFlex(b);
  if (!da || !db) return null;
  return Math.round((da.getTime() - db.getTime()) / 60000);
}

// ✅ NOVO: cálculo por "relógio" (HH:MM), ignorando a data.
// Útil porque fimProgramado vem com data de viagem e eta_ts_iso vem com data do runtime.
function minutesOfDay(value) {
  const d = parseDateFlex(value);
  if (!d) return null;
  return d.getHours() * 60 + d.getMinutes();
}

// diferença em minutos considerando somente HH:MM (ignora data).
// Ajuste de "virada de dia": escolhe o delta mais próximo (±12h).
function diffMinutesByClock(a, b) {
  const ma = minutesOfDay(a);
  const mb = minutesOfDay(b);
  if (ma == null || mb == null) return null;

  let delta = ma - mb;
  if (delta > 720) delta -= 1440;
  if (delta < -720) delta += 1440;
  return delta;
}

// sanity check: evita “38911 min”
function clampReasonableMinutes(mins, maxAbs = 12 * 60) {
  if (mins == null) return null;
  if (!Number.isFinite(mins)) return null;
  if (Math.abs(mins) > maxAbs) return null;
  return mins;
}

// =========================
// LISTVIEW
// =========================
export default function ListView({ setScreen }) {
  const [rows, setRows] = useState([]);
  const [lastRefresh, setLastRefresh] = useState(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [clock, setClock] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");

  // -------------------------
  // ✅ filtros por coluna
  // -------------------------
  // ✅ ALTERAÇÃO: inclui "vehicle_label" e troca chaves para os novos campos (nomePonto..., inicio..., fim..., eta_ts_iso)
  const [filters, setFilters] = useState({
    vehicle_label: "",
    route_short_name: "",
    direction_id: "",
    nomePontoInicio: "",
    nomePontoFim: "",
    inicioProgramado: "",
    inicioRealizado: "",
    fimProgramado: "",
    eta_ts_iso: "",
    delay_minutes: "",
    delay_departure_minutes: "",
    status: "",
    last_update_ts: "",
  });

  // (mantive sort state para não quebrar UI/ícones)
  const [sort, setSort] = useState({
    key: "eta_ts_iso",
    dir: "asc",
  });

  // =========================
  // ✅ FUNÇÕES DE LEITURA DOS CAMPOS (conforme sua especificação)
  // =========================
  function getOriginDesc(r) {
    // ✅ Origem: nomePontoInicio (somente)
    return (r?.nomePontoInicio ?? "").toString();
  }

  function getDestinationDesc(r) {
    // ✅ Destino: nomePontoFim (somente)
    return (r?.nomePontoFim ?? "").toString();
  }

  function getDirectionLabel(r) {
    // ✅ Sentido: I/V/C
    // C se origem == destino, senão direction_id: 0=I, 1=V
    const o = getOriginDesc(r).trim();
    const d = getDestinationDesc(r).trim();
    if (o && d && o === d) return "C";

    const di = r?.direction_id;
    if (di === 0) return "I";
    if (di === 1) return "V";
    return "—";
  }

  // =========================
  // ✅ Adapter: backend -> formato esperado pela tabela
  // =========================
  function normalizeRow(raw) {
    const r = { ...raw };

    // ✅ Campos exibidos (conforme pedido):
    // Veículo: vehicle_label (já vem)
    // Linha: route_short_name (já vem)
    // Origem/Destino: nomePontoInicio/nomePontoFim (já vem)
    // Partida Planejada/Real: inicioProgramado/inicioRealizado
    // Chegada Planejada: fimProgramado
    // ETA: eta_ts_iso
    //
    // Obs: aqui só garantimos que existam como chaves (sem inventar dados).
    r.vehicle_label = r.vehicle_label ?? null;
    r.route_short_name = r.route_short_name ?? null;

    r.nomePontoInicio = r.nomePontoInicio ?? null;
    r.nomePontoFim = r.nomePontoFim ?? null;

    r.inicioProgramado = r.inicioProgramado ?? null;
    r.inicioRealizado = r.inicioRealizado ?? null;
    r.fimProgramado = r.fimProgramado ?? null;

    // ✅ ETA vem do backend como eta_ts_iso
    r.eta_ts_iso = r.eta_ts_iso ?? null;

    // ✅ "Atualizado"
    r.last_update_ts = r.last_update_ts ?? null;

    // ✅ Regra final: "se o veículo não tiver nenhuma informação, não mostrar"
    // Considero "nenhuma informação útil" quando não tem nem prefixo, nem linha, nem origem/destino e nem tempos.
    const hasAnyInfo =
      (r.vehicle_label && String(r.vehicle_label).trim() !== "") ||
      (r.route_short_name && String(r.route_short_name).trim() !== "") ||
      (r.nomePontoInicio && String(r.nomePontoInicio).trim() !== "") ||
      (r.nomePontoFim && String(r.nomePontoFim).trim() !== "") ||
      r.inicioProgramado ||
      r.inicioRealizado ||
      r.fimProgramado ||
      r.eta_ts_iso ||
      r.last_update_ts;

    // ✅ REGRA NOVA: só mostrar veículos que tenham ORIGEM preenchida
    if (!r.nomePontoInicio || String(r.nomePontoInicio).trim() === "") {
      return null;
    }


    // ✅ Delay Partida: Partida Real - Partida Planejada (por relógio, ignorando data)
    r.delay_departure_minutes = clampReasonableMinutes(
      diffMinutesByClock(r.inicioRealizado, r.inicioProgramado),
      12 * 60
    );

    // ✅ Previsão: ETA - Chegada Planejada (por relógio, ignorando data)
    r.delay_minutes = clampReasonableMinutes(
      diffMinutesByClock(r.eta_ts_iso, r.fimProgramado),
      12 * 60
    );

    // ✅ Status: mesma ideia anterior (baseado no atraso/adiantamento da "previsão")
    {
      const dm = r.delay_minutes;
      if (dm == null) r.status = "unknown";
      else if (dm === 0) r.status = "on_time";
      else if (dm > 0) r.status = "delayed";
      else r.status = "early";
    }

    return r;
  }

  // -------------------------
  // ✅ carregar dados reais do backend
  // -------------------------
  async function loadVehiclesTable() {
    setLoading(true);
    setLoadError("");

    try {
      const url = "http://127.0.0.1:8000/map/vehicles/table";
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) {
        const txt = await res.text();
        throw new Error(`HTTP ${res.status} — ${txt.slice(0, 500)}`);
      }
      const data = await res.json();
      const items = Array.isArray(data) ? data : Array.isArray(data?.items) ? data.items : [];

      // ✅ ALTERAÇÃO: remove nulls (veículos sem informação)
      const normalized = items.map(normalizeRow).filter(Boolean);

      setRows(normalized);
      setLastRefresh(new Date());
    } catch (e) {
      setLoadError(e?.message || "Erro ao carregar dados.");
    } finally {
      setLoading(false);
    }
  }

  // ===== RELÓGIO =====
  useEffect(() => {
    const t = setInterval(() => {
      setClock(new Date().toLocaleTimeString());
    }, 1000);
    return () => clearInterval(t);
  }, []);

  // primeira carga + auto refresh
  useEffect(() => {
    loadVehiclesTable();
    const id = setInterval(loadVehiclesTable, 7000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // -------------------------
  // ✅ aplica filtros
  // -------------------------
  const filtered = useMemo(() => {
    const f = filters;

    function includesText(value, query) {
      if (!query) return true;
      const v = (value ?? "").toString().toLowerCase();
      const q = query.toString().toLowerCase().trim();
      return v.includes(q);
    }

    return rows.filter((r) => {
      // ✅ Veículo
      if (!includesText(r.vehicle_label, f.vehicle_label)) return false;

      // ✅ Linha
      if (!includesText(r.route_short_name, f.route_short_name)) return false;

      // ✅ Sentido (I/V/C)
      if (!includesText(getDirectionLabel(r), f.direction_id)) return false;

      // ✅ Origem/Destino (nomePonto*)
      if (!includesText(getOriginDesc(r), f.nomePontoInicio)) return false;
      if (!includesText(getDestinationDesc(r), f.nomePontoFim)) return false;

      // ✅ horários (mostrados como HH:MM, filtro por texto)
      if (!includesText(fmtHHMM(r.inicioProgramado), f.inicioProgramado)) return false;
      if (!includesText(fmtHHMM(r.inicioRealizado), f.inicioRealizado)) return false;
      if (!includesText(fmtHHMM(r.fimProgramado), f.fimProgramado)) return false;
      if (!includesText(fmtHHMM(r.eta_ts_iso), f.eta_ts_iso)) return false;

      // ✅ delays
      if (!includesText(formatDelay(r.delay_minutes), f.delay_minutes)) return false;
      if (!includesText(formatDelay(r.delay_departure_minutes), f.delay_departure_minutes)) return false;

      // ✅ status
      if (!includesText(r.status, f.status)) return false;

      // ✅ atualizado
      if (!includesText(fmtHHMMSS(r.last_update_ts), f.last_update_ts)) return false;

      return true;
    });
  }, [rows, filters]);

  // -------------------------
  // ✅ ordenação fixa: Destino (agrupado) -> ETA (crescente)
  // -------------------------
  const sorted = useMemo(() => {
    const copy = [...filtered];

    // ✅ ALTERAÇÃO: agora o ETA da tabela é eta_ts_iso
    function etaTs(row) {
      const d = parseDateFlex(row.eta_ts_iso);
      return d ? d.getTime() : Infinity;
    }

    copy.sort((a, b) => {
      // ✅ mantém agrupamento por destino (nomePontoFim)
      const da = getDestinationDesc(a).toLowerCase();
      const db = getDestinationDesc(b).toLowerCase();
      const c1 = da.localeCompare(db);
      if (c1 !== 0) return c1;

      // ✅ ETA dentro do destino
      const ea = etaTs(a);
      const eb = etaTs(b);
      if (ea < eb) return -1;
      if (ea > eb) return 1;

      // estabilidade: origem
      const oa = getOriginDesc(a).toLowerCase();
      const ob = getOriginDesc(b).toLowerCase();
      return oa.localeCompare(ob);
    });

    return copy;
  }, [filtered]);

  // =========================
  // STYLES
  // =========================
  const headerHeight = 50;

  const thStyle = {
    textAlign: "center",
    padding: "12px 10px",
    fontSize: 12,
    fontWeight: 800,
    borderBottom: "1px solid rgba(0,0,0,0.08)",
    whiteSpace: "nowrap",
    verticalAlign: "bottom",
  };

  const titleWrapStyle = {
    height: 28,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    textAlign: "center",
    fontSize: 12,
    fontWeight: 800,
    lineHeight: "14px",
  };

  const filterWrapStyle = {
    height: 28,
    display: "flex",
    alignItems: "flex-end",
    justifyContent: "center",
    paddingBottom: 2,
  };

  const filterInputStyle = {
    width: "70%",
    padding: "6px 8px",
    borderRadius: 8,
    border: "1px solid rgba(0,0,0,0.18)",
    outline: "none",
    fontSize: 12,
    textAlign: "center",
  };

  function thButtonStyle(active) {
    return {
      cursor: "pointer",
      userSelect: "none",
      opacity: active ? 1 : 0.85,
    };
  }

  function toggleSort(key) {
    setSort((s) => {
      if (s.key === key) {
        return { key, dir: s.dir === "asc" ? "desc" : "asc" };
      }
      return { key, dir: "asc" };
    });
  }

  function SortArrow({ activeKey }) {
    if (sort.key !== activeKey) return null;
    return <span style={{ marginLeft: 6 }}>{sort.dir === "asc" ? "▲" : "▼"}</span>;
  }

  return (
    <>
      {/* ================= HEADER ================= */}
      <div
        style={{
          position: "fixed",
          top: 0,
          left: 0,
          right: 0,
          height: headerHeight,
          background: "#35bfe6",
          color: "white",
          display: "flex",
          alignItems: "center",
          padding: "0 16px",
          zIndex: 2000,
        }}
      >
        <div
          style={{ cursor: "pointer", fontSize: 22, marginRight: 16 }}
          onClick={() => setMenuOpen(!menuOpen)}
        >
          ☰
        </div>

        <div
          style={{
            flex: 1,
            height: "100%",
            overflow: "hidden",
            display: "flex",
            alignItems: "center",
          }}
        >
          <img
            src={logo}
            alt="URBI"
            style={{
              height: 90,
              width: "auto",
              display: "block",
              objectFit: "cover",
            }}
          />
        </div>

        <div style={{ fontFamily: "monospace" }}>{clock}</div>
      </div>

      {/* ================= DRAWER ================= */}
      <div
        style={{
          position: "fixed",
          top: headerHeight,
          left: menuOpen ? 0 : -280,
          width: 260,
          height: `calc(100% - ${headerHeight}px)`,
          background: "#ffffff",
          boxShadow: menuOpen ? "2px 0 8px rgba(0,0,0,0.25)" : "none",
          transition: "left 0.3s",
          padding: 16,
          zIndex: 1900,
          pointerEvents: menuOpen ? "auto" : "none",
        }}
      >
        <h3 style={{ marginTop: 0 }}>Menu</h3>

        <button
          style={{
            width: "100%",
            padding: "10px 12px",
            marginBottom: 8,
            borderRadius: 10,
            border: "1px solid rgba(0,0,0,0.15)",
            background: "#ffffff",
            cursor: "pointer",
            textAlign: "left",
            fontWeight: 800,
          }}
          onClick={() => {
            setMenuOpen(false);
            setScreen?.("camadas");
          }}
        >
          🗺️ Camadas
        </button>

        <button
          style={{
            width: "100%",
            padding: "10px 12px",
            marginBottom: 14,
            borderRadius: 10,
            border: "1px solid rgba(0,0,0,0.15)",
            background: "#f7f7f7",
            cursor: "pointer",
            textAlign: "left",
            fontWeight: 800,
          }}
          onClick={() => {
            setMenuOpen(false);
            setScreen?.("lista");
          }}
        >
          📋 Lista
        </button>

        <hr style={{ margin: "14px 0" }} />

        <button
          onClick={() => loadVehiclesTable()}
          style={{
            width: "100%",
            background: "white",
            border: "1px solid rgba(0,0,0,0.15)",
            borderRadius: 12,
            padding: "10px 12px",
            cursor: "pointer",
            fontWeight: 800,
          }}
        >
          🔄 Atualizar agora
        </button>

        {loading && <div style={{ marginTop: 10, fontSize: 12, opacity: 0.75 }}>Carregando…</div>}
        {loadError && (
          <div style={{ marginTop: 10, fontSize: 12, color: "#b00020", fontWeight: 700 }}>
            Erro: {loadError}
          </div>
        )}
      </div>

      {/* ================= PAGE ================= */}
      <div
        style={{
          position: "absolute",
          top: headerHeight,
          left: 0,
          right: 0,
          bottom: 0,
          background: "#f6f7fb",
          overflow: "auto",
          padding: 16,
        }}
      >
        <div style={{ maxWidth: "95%", margin: "0 auto" }}>
          <div
            style={{
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
              gap: 16,
              marginBottom: 12,
            }}
          >
            <div>
              <div style={{ fontSize: 18, fontWeight: 800 }}>Lista operacional</div>
              <div style={{ fontSize: 12, opacity: 0.7 }}>
                Atualiza automaticamente • Última atualização:{" "}
                {lastRefresh ? lastRefresh.toLocaleTimeString() : "—"}
              </div>
            </div>

            <div style={{ fontSize: 12, opacity: 0.75, fontWeight: 700 }}>
              Resultados: {sorted.length}
            </div>
          </div>

          <div
            style={{
              background: "white",
              borderRadius: 14,
              boxShadow: "0 2px 10px rgba(0,0,0,0.08)",
              overflow: "hidden",
            }}
          >
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 1400 }}>
                <thead>
                  {/* ✅ TÍTULOS (ALTERAÇÃO: adiciona "Veículo" e ajusta nomes para os novos campos) */}
                  <tr style={{ background: "#ffffff", position: "sticky", top: 0, zIndex: 3 }}>
                    <th style={thStyle} onClick={() => toggleSort("vehicle_label")}>
                      <div style={{ ...titleWrapStyle, ...thButtonStyle(sort.key === "vehicle_label") }}>
                        Veículo <SortArrow activeKey="vehicle_label" />
                      </div>
                    </th>

                    <th style={thStyle} onClick={() => toggleSort("route_short_name")}>
                      <div style={{ ...titleWrapStyle, ...thButtonStyle(sort.key === "route_short_name") }}>
                        Linha <SortArrow activeKey="route_short_name" />
                      </div>
                    </th>

                    <th style={thStyle} onClick={() => toggleSort("direction_id")}>
                      <div style={{ ...titleWrapStyle, ...thButtonStyle(sort.key === "direction_id") }}>
                        Sentido <SortArrow activeKey="direction_id" />
                      </div>
                    </th>

                    <th style={thStyle} onClick={() => toggleSort("nomePontoInicio")}>
                      <div style={{ ...titleWrapStyle, ...thButtonStyle(sort.key === "nomePontoInicio") }}>
                        Origem <SortArrow activeKey="nomePontoInicio" />
                      </div>
                    </th>

                    <th style={thStyle} onClick={() => toggleSort("nomePontoFim")}>
                      <div style={{ ...titleWrapStyle, ...thButtonStyle(sort.key === "nomePontoFim") }}>
                        Destino <SortArrow activeKey="nomePontoFim" />
                      </div>
                    </th>

                    <th style={thStyle} onClick={() => toggleSort("inicioProgramado")}>
                      <div style={{ ...titleWrapStyle, ...thButtonStyle(sort.key === "inicioProgramado") }}>
                        Partida<br />Planejada <SortArrow activeKey="inicioProgramado" />
                      </div>
                    </th>

                    <th style={thStyle} onClick={() => toggleSort("inicioRealizado")}>
                      <div style={{ ...titleWrapStyle, ...thButtonStyle(sort.key === "inicioRealizado") }}>
                        Partida<br />Real <SortArrow activeKey="inicioRealizado" />
                      </div>
                    </th>

                    <th style={thStyle} onClick={() => toggleSort("fimProgramado")}>
                      <div style={{ ...titleWrapStyle, ...thButtonStyle(sort.key === "fimProgramado") }}>
                        Chegada<br />Planejada <SortArrow activeKey="fimProgramado" />
                      </div>
                    </th>

                    <th style={thStyle} onClick={() => toggleSort("eta_ts_iso")}>
                      <div style={{ ...titleWrapStyle, ...thButtonStyle(sort.key === "eta_ts_iso") }}>
                        ETA <SortArrow activeKey="eta_ts_iso" />
                      </div>
                    </th>

                    <th style={thStyle} onClick={() => toggleSort("delay_minutes")}>
                      <div style={{ ...titleWrapStyle, ...thButtonStyle(sort.key === "delay_minutes") }}>
                        Previsão <SortArrow activeKey="delay_minutes" />
                      </div>
                    </th>

                    <th style={thStyle} onClick={() => toggleSort("delay_departure_minutes")}>
                      <div style={{ ...titleWrapStyle, ...thButtonStyle(sort.key === "delay_departure_minutes") }}>
                        Delay<br />Partida <SortArrow activeKey="delay_departure_minutes" />
                      </div>
                    </th>

                    <th style={thStyle} onClick={() => toggleSort("status")}>
                      <div style={{ ...titleWrapStyle, ...thButtonStyle(sort.key === "status") }}>
                        Status <SortArrow activeKey="status" />
                      </div>
                    </th>

                    <th style={thStyle} onClick={() => toggleSort("last_update_ts")}>
                      <div style={{ ...titleWrapStyle, ...thButtonStyle(sort.key === "last_update_ts") }}>
                        Atualizado <SortArrow activeKey="last_update_ts" />
                      </div>
                    </th>
                  </tr>

                  {/* ✅ FILTROS (ALTERAÇÃO: reflete novas chaves) */}
                  <tr style={{ background: "#ffffff", position: "sticky", top: 56, zIndex: 2 }}>
                    {[
                      ["vehicle_label", "Ex: 336726"],
                      ["route_short_name", "Ex: 0882"],
                      ["direction_id", "I/V/C"],
                      ["nomePontoInicio", "Ex: 093"],
                      ["nomePontoFim", "Ex: 001"],
                      ["inicioProgramado", "HH:MM"],
                      ["inicioRealizado", "HH:MM"],
                      ["fimProgramado", "HH:MM"],
                      ["eta_ts_iso", "HH:MM"],
                      ["delay_minutes", "+7 / -2"],
                      ["delay_departure_minutes", "+3"],
                      ["status", "on_time"],
                      ["last_update_ts", "HH:MM:SS"],
                    ].map(([key, ph]) => (
                      <th key={key} style={{ ...thStyle, paddingTop: 6, paddingBottom: 8 }}>
                        <div style={filterWrapStyle}>
                          <input
                            value={filters[key]}
                            placeholder={ph}
                            onChange={(e) =>
                              setFilters((f) => ({
                                ...f,
                                [key]: e.target.value,
                              }))
                            }
                            style={filterInputStyle}
                          />
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>

                <tbody>
                  {sorted.map((r, idx) => (
                    <tr
                      key={`${r.vehicle_id ?? r.vehicle_label ?? idx}-${idx}`}
                      style={{
                        borderBottom: "1px solid rgba(0,0,0,0.06)",
                        background: idx % 2 === 0 ? "#ffffff" : "#fbfbfd",
                        textAlign: "center",
                      }}
                      title={[
                        `vehicle_id: ${r.vehicle_id ?? "—"}`,
                        `vehicle_label: ${r.vehicle_label ?? "—"}`,
                        `route_id: ${r.route_id ?? "—"}`,
                        `trip_id: ${r.trip_id || "—"}`,
                        `origin_stop_id: ${r.origin_stop_id ?? "—"}`,
                        `destination_stop_id: ${r.destination_stop_id ?? "—"}`,
                      ].join("\n")}
                    >
                      {/* ✅ ALTERAÇÃO: colunas conforme sua especificação */}
                      <td style={{ padding: "10px 10px", fontWeight: 800 }}>{r.vehicle_label || "—"}</td>
                      <td style={{ padding: "10px 10px", fontWeight: 800 }}>{r.route_short_name || "—"}</td>
                      <td style={{ padding: "10px 10px" }}>{getDirectionLabel(r)}</td>
                      <td style={{ padding: "10px 10px" }}>{r.nomePontoInicio || "—"}</td>
                      <td style={{ padding: "10px 10px" }}>{r.nomePontoFim || "—"}</td>
                      <td style={{ padding: "10px 10px" }}>{fmtHHMM(r.inicioProgramado)}</td>
                      <td style={{ padding: "10px 10px" }}>{fmtHHMM(r.inicioRealizado)}</td>
                      <td style={{ padding: "10px 10px" }}>{fmtHHMM(r.fimProgramado)}</td>
                      <td style={{ padding: "10px 10px" }}>{fmtHHMM(r.eta_ts_iso)}</td>
                      <td style={{ padding: "10px 10px", fontWeight: 700 }}>{formatDelay(r.delay_minutes)}</td>
                      <td style={{ padding: "10px 10px" }}>{formatDelay(r.delay_departure_minutes)}</td>
                      <td style={{ padding: "10px 10px" }}>
                        <span style={statusStyle(r.status)}>{(r.status || "unknown").toUpperCase()}</span>
                      </td>
                      <td style={{ padding: "10px 10px", fontFamily: "monospace" }}>{fmtHHMMSS(r.last_update_ts)}</td>
                    </tr>
                  ))}

                  {sorted.length === 0 && (
                    <tr>
                      <td colSpan={13} style={{ padding: 16, opacity: 0.7, textAlign: "center" }}>
                        Nenhum veículo ativo (ou filtros não retornaram resultados).
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div style={{ padding: 10, fontSize: 12, opacity: 0.75, textAlign: "center" }}>
              💡 Dica: passe o mouse numa linha para ver os campos ocultos (vehicle_id, trip_id, etc).
            </div>
          </div>
        </div>
      </div>
    </>
  );
}