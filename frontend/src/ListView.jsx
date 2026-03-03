import { useEffect, useMemo, useRef, useState } from "react";
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

// ✅ cálculo por "relógio" (HH:MM), ignorando a data.
function minutesOfDay(value) {
  const d = parseDateFlex(value);
  if (!d) return null;
  return d.getHours() * 60 + d.getMinutes();
}

// diferença em minutos considerando somente HH:MM (ignora data).
function diffMinutesByClock(a, b) {
  const ma = minutesOfDay(a);
  const mb = minutesOfDay(b);
  if (ma == null || mb == null) return null;

  let delta = ma - mb;
  if (delta > 720) delta -= 1440;
  if (delta < -720) delta += 1440;
  return delta;
}

// sanity check
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

  // =========================
  // ✅ Base CSV (terminais e atendimentos)
  // =========================
  const [baseRef, setBaseRef] = useState({
    atendimentos: [],
    terminais: [],
    linhasPorAtendimento: new Map(), // atendimento -> Set(linhas)
    terminalPorLinha: new Map(), // linha4 -> terminal (string)
  });

  // ✅ FIX: evita closure "congelada" (interval chama função antiga)
  const baseRefLive = useRef(baseRef);
  useEffect(() => {
    baseRefLive.current = baseRef;
  }, [baseRef]);

  const [groupFilters, setGroupFilters] = useState({
    atendimento: "",
    terminal: "",
  });

  // -------------------------
  // ✅ filtros por coluna
  // -------------------------
  const [filters, setFilters] = useState({
    vehicle_label: "",
    route_short_name: "",
    direction_id: "",
    terminal: "",
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

  const [sort, setSort] = useState({
    key: "eta_ts_iso",
    dir: "asc",
  });

  // =========================
  // ✅ Colunas colapsáveis
  // =========================
  // IMPORTANT: Para não desalinha a tabela, NUNCA removemos <td>/<th>.
  // Quando colapsado, mantemos a célula com width pequena e escondemos o conteúdo.
  const [colCollapsed, setColCollapsed] = useState({
    vehicle_label: false,
    route_short_name: false,
    direction_id: false,
    terminal: false,
    nomePontoInicio: false,
    nomePontoFim: false,
    inicioProgramado: false,
    inicioRealizado: false,
    fimProgramado: false,
    eta_ts_iso: false,
    delay_minutes: false,
    delay_departure_minutes: false,
    status: false,
    last_update_ts: false,
  });

  function toggleCol(key) {
    setColCollapsed((c) => ({ ...c, [key]: !c[key] }));
  }

  // =========================
  // ✅ FUNÇÕES DE LEITURA DOS CAMPOS
  // =========================
  function getOriginDesc(r) {
    return (r?.nomePontoInicio ?? "").toString();
  }

  function getDestinationDesc(r) {
    return (r?.nomePontoFim ?? "").toString();
  }

  function getDirectionLabel(r) {
    const o = getOriginDesc(r).trim();
    const d = getDestinationDesc(r).trim();
    if (o && d && o === d) return "C";

    const di = r?.direction_id;
    if (di === 0) return "I";
    if (di === 1) return "V";
    return "—";
  }

  // ✅ Terminal por Linha (CSV diz que é 1:1)
  // ✅ FIX: usa baseRefLive para não pegar Map vazio no intervalo
  function getTerminalFromLine(routeShortName) {
    const linha4 = (routeShortName ?? "").toString().trim().padStart(4, "0");
    return baseRefLive.current.terminalPorLinha.get(linha4) ?? "—";
  }

  // =========================
  // ✅ CSV loader com CACHE (localStorage) + debug
  // =========================
  useEffect(() => {
    const CACHE_KEY = "baseRef_v1";

    function safeJsonParse(s) {
      try {
        return JSON.parse(s);
      } catch {
        return null;
      }
    }

    function reviveBaseRef(obj) {
      // reconstroi Maps do JSON
      const terminalPorLinha = new Map(obj?.terminalPorLinhaEntries || []);
      const linhasPorAtendimento = new Map(
        (obj?.linhasPorAtendimentoEntries || []).map(([k, arr]) => [k, new Set(arr)])
      );

      return {
        atendimentos: Array.isArray(obj?.atendimentos) ? obj.atendimentos : [],
        terminais: Array.isArray(obj?.terminais) ? obj.terminais : [],
        linhasPorAtendimento,
        terminalPorLinha,
      };
    }

    function persistBaseRef(next) {
      // salva Maps como entries
      const payload = {
        atendimentos: next.atendimentos,
        terminais: next.terminais,
        terminalPorLinhaEntries: Array.from(next.terminalPorLinha.entries()),
        linhasPorAtendimentoEntries: Array.from(next.linhasPorAtendimento.entries()).map(([k, set]) => [
          k,
          Array.from(set),
        ]),
        savedAt: new Date().toISOString(),
      };
      localStorage.setItem(CACHE_KEY, JSON.stringify(payload));
    }

    async function loadBaseRef() {
      // 1) tenta cache primeiro
      const cached = safeJsonParse(localStorage.getItem(CACHE_KEY));
      if (cached) {
        const revived = reviveBaseRef(cached);
        setBaseRef(revived);
        console.log("[baseRef] carregado do cache:", {
          terminais: revived.terminais.length,
          atendimentos: revived.atendimentos.length,
          terminalPorLinha: revived.terminalPorLinha.size,
          savedAt: cached.savedAt,
        });
      }

      // 2) sempre tenta baixar do arquivo pra atualizar
      try {
        const res = await fetch("/base_terminais_atendimentos.csv", { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const textRaw = await res.text();

        const text = textRaw.replace(/^\uFEFF/, "").trim();
        const lines = text
          .split(/\r?\n/)
          .map((l) => l.trim())
          .filter(Boolean);

        if (lines.length <= 1) throw new Error("CSV vazio/sem linhas");

        // detecta delimitador
        const headerLine = lines[0];
        const delim = headerLine.includes(";") ? ";" : ",";

        const header = headerLine
          .split(delim)
          .map((h) => h.replace(/^\uFEFF/, "").trim());

        const idxLinha = header.findIndex((h) => h.toLowerCase() === "linha");
        const idxTerminal = header.findIndex((h) => h.toLowerCase() === "terminal");
        const idxAt = header.findIndex((h) => h.toLowerCase() === "atendimento");

        if (idxLinha < 0) throw new Error(`CSV sem coluna [Linha]. Headers: ${header.join(" | ")}`);
        if (idxTerminal < 0) throw new Error(`CSV sem coluna [Terminal]. Headers: ${header.join(" | ")}`);
        if (idxAt < 0) throw new Error(`CSV sem coluna [Atendimento]. Headers: ${header.join(" | ")}`);

        const linhasPorAtendimento = new Map();
        const terminalPorLinha = new Map();
        const atendimentosSet = new Set();
        const terminaisSet = new Set();

        for (let i = 1; i < lines.length; i++) {
          const cols = lines[i].split(delim).map((c) => c.trim());

          const linhaRaw = (cols[idxLinha] ?? "").trim();
          const terminalRaw = (cols[idxTerminal] ?? "").trim();
          const atendimento = (cols[idxAt] ?? "").trim();

          if (!linhaRaw || !terminalRaw) continue;

          // ✅ chave: linha sempre 4 dígitos
          const linha4 = String(linhaRaw).trim().padStart(4, "0");
          const terminal = String(terminalRaw).trim();

          terminalPorLinha.set(linha4, terminal);
          terminaisSet.add(terminal);

          if (atendimento) {
            atendimentosSet.add(atendimento);
            if (!linhasPorAtendimento.has(atendimento)) linhasPorAtendimento.set(atendimento, new Set());
            linhasPorAtendimento.get(atendimento).add(linha4);
          }
        }

        const next = {
          atendimentos: Array.from(atendimentosSet).sort((a, b) => a.localeCompare(b)),
          terminais: Array.from(terminaisSet).sort((a, b) => a.localeCompare(b)),
          linhasPorAtendimento,
          terminalPorLinha,
        };

        setBaseRef(next);
        persistBaseRef(next);

        console.log("==== DEBUG BASE REF ====");
        console.log("Total linhas mapeadas:", next.terminalPorLinha.size);

        const exemplo = Array.from(next.terminalPorLinha.entries()).slice(0, 10);
        console.log("Primeiras 10 linhas do CSV:", exemplo);
        console.log("[baseRef] carregado do CSV e salvo em cache:", {
          terminais: next.terminais.length,
          atendimentos: next.atendimentos.length,
          terminalPorLinha: next.terminalPorLinha.size,
        });
      } catch (e) {
        console.warn("[baseRef] falhou atualizar do CSV, mantendo cache se existir:", e?.message || e);
      }
    }

    loadBaseRef();
  }, []);

  // =========================
  // ✅ Adapter: backend -> formato esperado pela tabela
  // =========================
  function normalizeRow(raw) {
    const r = { ...raw };

    r.vehicle_label = r.vehicle_label ?? null;
    r.route_short_name = r.route_short_name ?? null;

    r.nomePontoInicio = r.nomePontoInicio ?? null;
    r.nomePontoFim = r.nomePontoFim ?? null;

    r.inicioProgramado = r.inicioProgramado ?? null;
    r.inicioRealizado = r.inicioRealizado ?? null;
    r.fimProgramado = r.fimProgramado ?? null;

    r.eta_ts_iso = r.eta_ts_iso ?? null;
    r.last_update_ts = r.last_update_ts ?? null;

    // ✅ regra: só mostrar veículos que tenham ORIGEM preenchida
    if (!r.nomePontoInicio || String(r.nomePontoInicio).trim() === "") {
      return null;
    }

    // ✅ coluna Terminal (derivada do CSV via Linha)
    r.terminal = getTerminalFromLine(r.route_short_name);

    // ✅ Delay Partida
    r.delay_departure_minutes = clampReasonableMinutes(
      diffMinutesByClock(r.inicioRealizado, r.inicioProgramado),
      12 * 60
    );

    // ✅ Previsão
    r.delay_minutes = clampReasonableMinutes(diffMinutesByClock(r.eta_ts_iso, r.fimProgramado), 12 * 60);

    // ✅ Status
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
      // ✅ filtro por Grupo (Atendimento) => restringe LINHAS
      if (groupFilters.atendimento) {
        const setLinhas = baseRef.linhasPorAtendimento.get(groupFilters.atendimento);
        if (!setLinhas) return false;
        const linha = (r.route_short_name ?? "").toString().padStart(4, "0");
        if (!setLinhas.has(linha)) return false;
      }

      // ✅ filtro por Terminal (dropdown) => aplica na coluna terminal
      if (groupFilters.terminal) {
        const term = String(groupFilters.terminal).trim();
        if ((r.terminal ?? "").toString().trim() !== term) return false;
      }

      if (!includesText(r.vehicle_label, f.vehicle_label)) return false;
      if (!includesText(r.route_short_name, f.route_short_name)) return false;

      if (!includesText(getDirectionLabel(r), f.direction_id)) return false;

      if (!includesText(r.terminal, f.terminal)) return false;

      if (!includesText(getOriginDesc(r), f.nomePontoInicio)) return false;
      if (!includesText(getDestinationDesc(r), f.nomePontoFim)) return false;

      if (!includesText(fmtHHMM(r.inicioProgramado), f.inicioProgramado)) return false;
      if (!includesText(fmtHHMM(r.inicioRealizado), f.inicioRealizado)) return false;
      if (!includesText(fmtHHMM(r.fimProgramado), f.fimProgramado)) return false;
      if (!includesText(fmtHHMM(r.eta_ts_iso), f.eta_ts_iso)) return false;

      if (!includesText(formatDelay(r.delay_minutes), f.delay_minutes)) return false;
      if (!includesText(formatDelay(r.delay_departure_minutes), f.delay_departure_minutes)) return false;

      if (!includesText(r.status, f.status)) return false;

      if (!includesText(fmtHHMMSS(r.last_update_ts), f.last_update_ts)) return false;

      return true;
    });
  }, [rows, filters, groupFilters, baseRef]);

  // -------------------------
  // ✅ ordenação fixa: Destino (agrupado) -> ETA (crescente)
  // -------------------------
  const sorted = useMemo(() => {
    const copy = [...filtered];

    function etaTs(row) {
      const d = parseDateFlex(row.eta_ts_iso);
      return d ? d.getTime() : Infinity;
    }

    copy.sort((a, b) => {
      const da = getDestinationDesc(a).toLowerCase();
      const db = getDestinationDesc(b).toLowerCase();
      const c1 = da.localeCompare(db);
      if (c1 !== 0) return c1;

      const ea = etaTs(a);
      const eb = etaTs(b);
      if (ea < eb) return -1;
      if (ea > eb) return 1;

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
    gap: 8,
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

  // ✅ botão +/- SEMPRE disponível no header
  function ColToggleBtn({ colKey }) {
    const collapsed = !!colCollapsed[colKey];
    return (
      <button
        onClick={(e) => {
          e.stopPropagation();
          toggleCol(colKey);
        }}
        title={collapsed ? "Reabrir coluna" : "Colapsar coluna"}
        style={{
          border: "1px solid rgba(0,0,0,0.18)",
          background: "white",
          borderRadius: 8,
          width: 22,
          height: 22,
          lineHeight: "20px",
          fontSize: 14,
          fontWeight: 900,
          cursor: "pointer",
          flex: "0 0 auto",
        }}
      >
        {collapsed ? "+" : "−"}
      </button>
    );
  }

  // ✅ colunas na ordem
  const COLS = [
    { key: "vehicle_label", label: "Veículo", sortKey: "vehicle_label" },
    { key: "route_short_name", label: "Linha", sortKey: "route_short_name" },
    { key: "direction_id", label: "Sentido", sortKey: "direction_id" },
    { key: "terminal", label: "Terminal", sortKey: "terminal" },
    { key: "nomePontoInicio", label: "Origem", sortKey: "nomePontoInicio" },
    { key: "nomePontoFim", label: "Destino", sortKey: "nomePontoFim" },
    { key: "inicioProgramado", label: "Partida\nPlanejada", sortKey: "inicioProgramado" },
    { key: "inicioRealizado", label: "Partida\nReal", sortKey: "inicioRealizado" },
    { key: "fimProgramado", label: "Chegada\nPlanejada", sortKey: "fimProgramado" },
    { key: "eta_ts_iso", label: "ETA", sortKey: "eta_ts_iso" },
    { key: "delay_minutes", label: "Previsão", sortKey: "delay_minutes" },
    { key: "delay_departure_minutes", label: "Delay\nPartida", sortKey: "delay_departure_minutes" },
    { key: "status", label: "Status", sortKey: "status" },
    { key: "last_update_ts", label: "Atualizado", sortKey: "last_update_ts" },
  ];

  // ✅ layout consistente: célula sempre existe, mas pode ficar "fininha" e com conteúdo escondido
  function cellStyleFor(colKey) {
    const collapsed = !!colCollapsed[colKey];
    if (!collapsed) return { padding: "10px 10px" };

    // célula "fininha" mantém o grid alinhado e o botão do header continua funcionando
    return {
      padding: "10px 6px",
      width: 44,
      maxWidth: 44,
      minWidth: 44,
      overflow: "hidden",
      whiteSpace: "nowrap",
    };
  }

  function headerStyleFor(colKey) {
    const collapsed = !!colCollapsed[colKey];
    if (!collapsed) return thStyle;
    return {
      ...thStyle,
      paddingLeft: 6,
      paddingRight: 6,
      width: 44,
      maxWidth: 44,
      minWidth: 44,
    };
  }

  // ✅ conteúdo some, mas a célula fica
  function HiddenCellContent() {
    return <span style={{ opacity: 0.6, fontSize: 11 }}></span>;
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
        <div style={{ cursor: "pointer", fontSize: 22, marginRight: 16 }} onClick={() => setMenuOpen(!menuOpen)}>
          ☰
        </div>

        <div style={{ flex: 1, height: "100%", overflow: "hidden", display: "flex", alignItems: "center" }}>
          <img src={logo} alt="URBI" style={{ height: 90, width: "auto", display: "block", objectFit: "cover" }} />
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
                Atualiza automaticamente • Última atualização: {lastRefresh ? lastRefresh.toLocaleTimeString() : "—"}
              </div>
            </div>

            <div style={{ fontSize: 12, opacity: 0.75, fontWeight: 700 }}>Resultados: {sorted.length}</div>
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
                  {/* ✅ TÍTULOS (header sempre visível) */}
                  <tr style={{ background: "#ffffff", position: "sticky", top: 0, zIndex: 3 }}>
                    {COLS.map((c) => {
                      const collapsed = !!colCollapsed[c.key];
                      const parts = String(c.label).split("\n");

                      return (
                        <th key={c.key} style={headerStyleFor(c.key)} onClick={() => toggleSort(c.sortKey)}>
                          <div style={{ ...titleWrapStyle, ...thButtonStyle(sort.key === c.sortKey) }}>
                            <ColToggleBtn colKey={c.key} />
                            {!collapsed ? (
                              <div>
                                {parts[0]}
                                {parts[1] ? (
                                  <>
                                    <br />
                                    {parts[1]}
                                  </>
                                ) : null}
                                <SortArrow activeKey={c.sortKey} />
                              </div>
                            ) : (
                              <HiddenCellContent />
                            )}
                          </div>
                        </th>
                      );
                    })}
                  </tr>

                  {/* ✅ linha extra (Grupo/Terminal) */}
                  <tr style={{ background: "#ffffff", position: "sticky", top: 56, zIndex: 2 }}>
                    {COLS.map((c) => {
                      const collapsed = !!colCollapsed[c.key];

                      // ✅ mantém <th> SEMPRE, pra não desalinha
                      if (collapsed) {
                        return <th key={c.key} style={headerStyleFor(c.key)} />;
                      }

                      if (c.key === "route_short_name") {
                        return (
                          <th key={c.key} style={{ ...thStyle, paddingTop: 6, paddingBottom: 8 }}>
                            <div style={filterWrapStyle}>
                              <select
                                value={groupFilters.atendimento}
                                onChange={(e) => setGroupFilters((g) => ({ ...g, atendimento: e.target.value }))}
                                style={{ ...filterInputStyle, width: "85%" }}
                              >
                                <option value="">(Todos os grupos)</option>
                                {baseRef.atendimentos.map((a) => (
                                  <option key={a} value={a}>
                                    {a}
                                  </option>
                                ))}
                              </select>
                            </div>
                          </th>
                        );
                      }

                      if (c.key === "terminal") {
                        return (
                          <th key={c.key} style={{ ...thStyle, paddingTop: 6, paddingBottom: 8 }}>
                            <div style={filterWrapStyle}>
                              <select
                                value={groupFilters.terminal}
                                onChange={(e) => setGroupFilters((g) => ({ ...g, terminal: e.target.value }))}
                                style={{ ...filterInputStyle, width: "85%" }}
                              >
                                <option value="">(Todos os terminais)</option>
                                {baseRef.terminais.map((t) => (
                                  <option key={t} value={t}>
                                    {t}
                                  </option>
                                ))}
                              </select>
                            </div>
                          </th>
                        );
                      }

                      return <th key={c.key} style={{ ...thStyle, paddingTop: 6, paddingBottom: 8 }} />;
                    })}
                  </tr>

                  {/* ✅ filtros por coluna */}
                  <tr style={{ background: "#ffffff", position: "sticky", top: 112, zIndex: 1 }}>
                    {COLS.map((c) => {
                      const collapsed = !!colCollapsed[c.key];

                      // ✅ mantém <th> SEMPRE, pra não desalinha
                      if (collapsed) {
                        return <th key={c.key} style={headerStyleFor(c.key)} />;
                      }

                      const placeholders = {
                        vehicle_label: "Ex: 336726",
                        route_short_name: "Ex: 0882",
                        direction_id: "I/V/C",
                        terminal: "Ex: 093",
                        nomePontoInicio: "Ex: 093",
                        nomePontoFim: "Ex: 001",
                        inicioProgramado: "HH:MM",
                        inicioRealizado: "HH:MM",
                        fimProgramado: "HH:MM",
                        eta_ts_iso: "HH:MM",
                        delay_minutes: "+7 / -2",
                        delay_departure_minutes: "+3",
                        status: "on_time",
                        last_update_ts: "HH:MM:SS",
                      };

                      return (
                        <th key={c.key} style={{ ...thStyle, paddingTop: 6, paddingBottom: 8 }}>
                          <div style={filterWrapStyle}>
                            <input
                              value={filters[c.key] ?? ""}
                              placeholder={placeholders[c.key] ?? ""}
                              onChange={(e) =>
                                setFilters((f) => ({
                                  ...f,
                                  [c.key]: e.target.value,
                                }))
                              }
                              style={filterInputStyle}
                            />
                          </div>
                        </th>
                      );
                    })}
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
                      {/* ✅ BODY: sempre renderiza todas as células (mantém alinhamento) */}
                      <td style={{ ...cellStyleFor("vehicle_label"), fontWeight: 800 }}>
                        {colCollapsed.vehicle_label ? <HiddenCellContent /> : r.vehicle_label || "—"}
                      </td>

                      <td style={{ ...cellStyleFor("route_short_name"), fontWeight: 800 }}>
                        {colCollapsed.route_short_name ? <HiddenCellContent /> : r.route_short_name || "—"}
                      </td>

                      <td style={cellStyleFor("direction_id")}>
                        {colCollapsed.direction_id ? <HiddenCellContent /> : getDirectionLabel(r)}
                      </td>

                      <td style={cellStyleFor("terminal")}>
                        {colCollapsed.terminal ? <HiddenCellContent /> : r.terminal || "—"}
                      </td>

                      <td style={cellStyleFor("nomePontoInicio")}>
                        {colCollapsed.nomePontoInicio ? <HiddenCellContent /> : r.nomePontoInicio || "—"}
                      </td>

                      <td style={cellStyleFor("nomePontoFim")}>
                        {colCollapsed.nomePontoFim ? <HiddenCellContent /> : r.nomePontoFim || "—"}
                      </td>

                      <td style={cellStyleFor("inicioProgramado")}>
                        {colCollapsed.inicioProgramado ? <HiddenCellContent /> : fmtHHMM(r.inicioProgramado)}
                      </td>

                      <td style={cellStyleFor("inicioRealizado")}>
                        {colCollapsed.inicioRealizado ? <HiddenCellContent /> : fmtHHMM(r.inicioRealizado)}
                      </td>

                      <td style={cellStyleFor("fimProgramado")}>
                        {colCollapsed.fimProgramado ? <HiddenCellContent /> : fmtHHMM(r.fimProgramado)}
                      </td>

                      <td style={cellStyleFor("eta_ts_iso")}>
                        {colCollapsed.eta_ts_iso ? <HiddenCellContent /> : fmtHHMM(r.eta_ts_iso)}
                      </td>

                      <td style={{ ...cellStyleFor("delay_minutes"), fontWeight: 700 }}>
                        {colCollapsed.delay_minutes ? <HiddenCellContent /> : formatDelay(r.delay_minutes)}
                      </td>

                      <td style={cellStyleFor("delay_departure_minutes")}>
                        {colCollapsed.delay_departure_minutes ? <HiddenCellContent /> : formatDelay(r.delay_departure_minutes)}
                      </td>

                      <td style={cellStyleFor("status")}>
                        {colCollapsed.status ? (
                          <HiddenCellContent />
                        ) : (
                          <span style={statusStyle(r.status)}>{(r.status || "unknown").toUpperCase()}</span>
                        )}
                      </td>

                      <td style={{ ...cellStyleFor("last_update_ts"), fontFamily: "monospace" }}>
                        {colCollapsed.last_update_ts ? <HiddenCellContent /> : fmtHHMMSS(r.last_update_ts)}
                      </td>
                    </tr>
                  ))}

                  {sorted.length === 0 && (
                    <tr>
                      <td colSpan={COLS.length} style={{ padding: 16, opacity: 0.7, textAlign: "center" }}>
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