import { useEffect, useMemo, useState } from "react";
import logo from "./assets/logo.png";

// =========================
// MOCK DATA (por enquanto)
// =========================

function randomInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function pad2(n) {
  return String(n).padStart(2, "0");
}

function fmtHHMM(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

function fmtHHMMSS(isoOrTs) {
  if (!isoOrTs) return "—";

  let d;
  if (typeof isoOrTs === "number") {
    d = new Date(isoOrTs * 1000);
  } else {
    d = new Date(isoOrTs);
  }

  if (isNaN(d.getTime())) return "—";
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
}

function buildMockRow(i) {
  const now = new Date();

  const planned = new Date(now.getTime() + randomInt(-45, 60) * 60 * 1000);
  const hasPlan = Math.random() > 0.15;

  const hasReal = Math.random() > 0.35;
  const real = new Date(planned.getTime() + randomInt(-5, 15) * 60 * 1000);

  const hasEta = Math.random() > 0.15;
  const eta = new Date(now.getTime() + randomInt(2, 55) * 60 * 1000);

  const delayMinutes = randomInt(-4, 18);
  const delayDepartureMinutes = hasReal ? Math.round((real - planned) / 60000) : null;

  let status = "unknown";
  if (hasPlan) {
    if (delayMinutes === 0) status = "on_time";
    else if (delayMinutes > 0) status = "delayed";
    else status = "early";
  }

  return {
    // =========================
    // COLUNAS OBRIGATÓRIAS
    // =========================
    route_short_name: String(randomInt(600, 9999)).padStart(4, "0"),
    direction_id: Math.random() > 0.5 ? 0 : 1,
    origin_desc: String(randomInt(1, 400)).padStart(3, "0"),
    destination_desc: String(randomInt(1, 400)).padStart(3, "0"),

    departure_planned_local: hasPlan ? planned.toISOString() : null,
    departure_realized_local: hasReal ? real.toISOString() : null,
    arrival_planned_local: hasPlan
      ? new Date(planned.getTime() + randomInt(20, 80) * 60 * 1000).toISOString()
      : null,
    eta_local: hasEta ? eta.toISOString() : null,

    delay_minutes: hasPlan ? delayMinutes : null,
    delay_departure_minutes: hasPlan ? delayDepartureMinutes : null,

    status,
    last_update_ts: new Date(now.getTime() - randomInt(1, 70) * 1000).toISOString(),

    // =========================
    // CAMPOS OCULTOS (debug)
    // =========================
    vehicle_id: `V-${10000 + i}`,
    vehicle_label: `${randomInt(1000, 9999)}`,
    route_id: `R-${randomInt(1, 2000)}`,
    trip_id: Math.random() > 0.2 ? `T-${randomInt(1, 999999)}` : null,

    origin_stop_id: `STOP-${randomInt(100000, 999999)}`,
    destination_stop_id: `STOP-${randomInt(100000, 999999)}`,
  };
}

// =========================
// UI HELPERS
// =========================

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

// =========================
// LISTVIEW
// =========================
export default function ListView({ setScreen }) {
  const [rows, setRows] = useState([]);
  const [lastRefresh, setLastRefresh] = useState(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [clock, setClock] = useState("");

  // -------------------------
  // ✅ filtros por coluna
  // -------------------------
  const [filters, setFilters] = useState({
    route_short_name: "",
    direction_id: "",
    origin_desc: "",
    destination_desc: "",
    departure_planned_local: "",
    departure_realized_local: "",
    arrival_planned_local: "",
    eta_local: "",
    delay_minutes: "",
    delay_departure_minutes: "",
    status: "",
    last_update_ts: "",
  });

  // -------------------------
  // ✅ ordenação por coluna
  // -------------------------
  const [sort, setSort] = useState({
    key: "departure_planned_local",
    dir: "asc", // "asc" | "desc"
  });

  // ===== RELÓGIO =====
  useEffect(() => {
    const t = setInterval(() => {
      setClock(new Date().toLocaleTimeString());
    }, 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    function loadMock() {
      const n = randomInt(18, 35);
      const items = Array.from({ length: n }, (_, i) => buildMockRow(i + 1));
      setRows(items);
      setLastRefresh(new Date());
    }

    loadMock();
    const id = setInterval(loadMock, 7000);
    return () => clearInterval(id);
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
      // texto/num
      if (!includesText(r.route_short_name, f.route_short_name)) return false;
      if (!includesText(r.direction_id, f.direction_id)) return false;
      if (!includesText(r.origin_desc, f.origin_desc)) return false;
      if (!includesText(r.destination_desc, f.destination_desc)) return false;

      // datas mostradas como HH:MM, mas filtro funciona como "texto"
      if (!includesText(fmtHHMM(r.departure_planned_local), f.departure_planned_local)) return false;
      if (!includesText(fmtHHMM(r.departure_realized_local), f.departure_realized_local)) return false;
      if (!includesText(fmtHHMM(r.arrival_planned_local), f.arrival_planned_local)) return false;
      if (!includesText(fmtHHMM(r.eta_local), f.eta_local)) return false;

      // delays
      if (!includesText(formatDelay(r.delay_minutes), f.delay_minutes)) return false;
      if (!includesText(formatDelay(r.delay_departure_minutes), f.delay_departure_minutes)) return false;

      // status
      if (!includesText(r.status, f.status)) return false;

      // atualizado
      if (!includesText(fmtHHMMSS(r.last_update_ts), f.last_update_ts)) return false;

      return true;
    });
  }, [rows, filters]);

  // -------------------------
  // ✅ aplica ordenação
  // -------------------------
  const sorted = useMemo(() => {
    const copy = [...filtered];

    function sortValue(row, key) {
      const v = row[key];

      // datas ISO: ordenar por timestamp
      if (
        key === "departure_planned_local" ||
        key === "departure_realized_local" ||
        key === "arrival_planned_local" ||
        key === "eta_local"
      ) {
        return v ? new Date(v).getTime() : Infinity;
      }

      // números
      if (key === "direction_id") return row.direction_id ?? Infinity;
      if (key === "delay_minutes") return row.delay_minutes ?? Infinity;
      if (key === "delay_departure_minutes") return row.delay_departure_minutes ?? Infinity;

      // texto
      return (v ?? "").toString().toLowerCase();
    }

    copy.sort((a, b) => {
      const av = sortValue(a, sort.key);
      const bv = sortValue(b, sort.key);

      if (av < bv) return sort.dir === "asc" ? -1 : 1;
      if (av > bv) return sort.dir === "asc" ? 1 : -1;

      // critério secundário fixo para estabilidade
      const ad = a.destination_desc || "";
      const bd = b.destination_desc || "";
      return ad.localeCompare(bd);
    });

    return copy;
  }, [filtered, sort]);

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
    alignItems: "flex-end", // ✅ alinha todos na mesma linha
    justifyContent: "center",
    paddingBottom: 2,
  };

  const filterInputStyle = {
    width: "70%", // ✅ pedido: 70% da coluna
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
          onClick={() => {
            const n = randomInt(18, 35);
            setRows(Array.from({ length: n }, (_, i) => buildMockRow(i + 1)));
            setLastRefresh(new Date());
          }}
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
              <div style={{ fontSize: 18, fontWeight: 800 }}>
                Lista operacional (mockup)
              </div>
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
              <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 1300 }}>
                <thead>
                  {/* ✅ TÍTULOS */}
                  <tr style={{ background: "#ffffff", position: "sticky", top: 0, zIndex: 3 }}>
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

                    <th style={thStyle} onClick={() => toggleSort("origin_desc")}>
                      <div style={{ ...titleWrapStyle, ...thButtonStyle(sort.key === "origin_desc") }}>
                        Origem <SortArrow activeKey="origin_desc" />
                      </div>
                    </th>

                    <th style={thStyle} onClick={() => toggleSort("destination_desc")}>
                      <div style={{ ...titleWrapStyle, ...thButtonStyle(sort.key === "destination_desc") }}>
                        Destino <SortArrow activeKey="destination_desc" />
                      </div>
                    </th>

                    <th style={thStyle} onClick={() => toggleSort("departure_planned_local")}>
                      <div style={{ ...titleWrapStyle, ...thButtonStyle(sort.key === "departure_planned_local") }}>
                        Partida<br />Planejada <SortArrow activeKey="departure_planned_local" />
                      </div>
                    </th>

                    <th style={thStyle} onClick={() => toggleSort("departure_realized_local")}>
                      <div style={{ ...titleWrapStyle, ...thButtonStyle(sort.key === "departure_realized_local") }}>
                        Partida<br />Real <SortArrow activeKey="departure_realized_local" />
                      </div>
                    </th>

                    <th style={thStyle} onClick={() => toggleSort("arrival_planned_local")}>
                      <div style={{ ...titleWrapStyle, ...thButtonStyle(sort.key === "arrival_planned_local") }}>
                        Chegada<br />Planejada <SortArrow activeKey="arrival_planned_local" />
                      </div>
                    </th>

                    <th style={thStyle} onClick={() => toggleSort("eta_local")}>
                      <div style={{ ...titleWrapStyle, ...thButtonStyle(sort.key === "eta_local") }}>
                        ETA <SortArrow activeKey="eta_local" />
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

                  {/* ✅ FILTROS (ALINHADOS) */}
                  <tr style={{ background: "#ffffff", position: "sticky", top: 56, zIndex: 2 }}>
                    {[
                      ["route_short_name", "Ex: 0882"],
                      ["direction_id", "0/1"],
                      ["origin_desc", "Ex: 262"],
                      ["destination_desc", "Ex: 001"],
                      ["departure_planned_local", "HH:MM"],
                      ["departure_realized_local", "HH:MM"],
                      ["arrival_planned_local", "HH:MM"],
                      ["eta_local", "HH:MM"],
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
                      key={`${r.vehicle_id}-${idx}`}
                      style={{
                        borderBottom: "1px solid rgba(0,0,0,0.06)",
                        background: idx % 2 === 0 ? "#ffffff" : "#fbfbfd",
                        textAlign: "center",
                      }}
                      title={[
                        `vehicle_id: ${r.vehicle_id}`,
                        `vehicle_label: ${r.vehicle_label}`,
                        `route_id: ${r.route_id}`,
                        `trip_id: ${r.trip_id || "—"}`,
                        `origin_stop_id: ${r.origin_stop_id}`,
                        `destination_stop_id: ${r.destination_stop_id}`,
                      ].join("\n")}
                    >
                      <td style={{ padding: "10px 10px", fontWeight: 800 }}>{r.route_short_name || "—"}</td>
                      <td style={{ padding: "10px 10px" }}>{r.direction_id ?? "—"}</td>
                      <td style={{ padding: "10px 10px" }}>{r.origin_desc || "—"}</td>
                      <td style={{ padding: "10px 10px" }}>{r.destination_desc || "—"}</td>
                      <td style={{ padding: "10px 10px" }}>{fmtHHMM(r.departure_planned_local)}</td>
                      <td style={{ padding: "10px 10px" }}>{fmtHHMM(r.departure_realized_local)}</td>
                      <td style={{ padding: "10px 10px" }}>{fmtHHMM(r.arrival_planned_local)}</td>
                      <td style={{ padding: "10px 10px" }}>{fmtHHMM(r.eta_local)}</td>
                      <td style={{ padding: "10px 10px", fontWeight: 700 }}>{formatDelay(r.delay_minutes)}</td>
                      <td style={{ padding: "10px 10px" }}>{formatDelay(r.delay_departure_minutes)}</td>
                      <td style={{ padding: "10px 10px" }}>
                        <span style={statusStyle(r.status)}>{r.status}</span>
                      </td>
                      <td style={{ padding: "10px 10px", fontFamily: "monospace" }}>{fmtHHMMSS(r.last_update_ts)}</td>
                    </tr>
                  ))}

                  {sorted.length === 0 && (
                    <tr>
                      <td colSpan={12} style={{ padding: 16, opacity: 0.7, textAlign: "center" }}>
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
