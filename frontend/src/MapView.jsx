import {
  MapContainer,
  TileLayer,
  Polyline,
  Marker,
  Popup,
  ZoomControl,
  LayersControl,
  useMapEvents
} from "react-leaflet";
import { useEffect, useMemo, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import logo from "./assets/logo.png";

const { BaseLayer } = LayersControl;
const API = "http://127.0.0.1:8000";

// ================= ICON =================
const circleIcon = (color = "#999") =>
  L.divIcon({
    html: `
      <svg width="16" height="16">
        <circle cx="8" cy="8" r="6"
          fill="${color}" stroke="white" stroke-width="2" />
      </svg>
    `,
    className: "",
    iconSize: [16, 16],
    iconAnchor: [8, 8],
  });

// ============ COLOR SCALE (VELOCIDADE) ============
function speedColor(v) {
  if (v == null) return "#cccccc";
  if (v < 10) return "#800080";
  if (v < 15) return "#ff0000";
  if (v < 20) return "#ff8800";
  if (v < 30) return "#ffdd00";
  return "#00aa00";
}

// ============ COLOR SCALE (COMPARAÇÃO) ============
function comparisonColor(c) {
  if (!c) return "#cccccc";
  return {
    green: "#00aa00",
    dark_green: "#006400",
    yellow: "#ffdd00",
    orange: "#ff8800",
    red: "#ff0000",
    purple: "#800080"
  }[c] || "#cccccc";
}

// ================= LEGENDS =================
const legendBoxStyle = {
  background: "white",
  padding: 10,
  borderRadius: 6,
  boxShadow: "0 2px 6px rgba(0,0,0,0.3)",
  fontSize: 12,
  marginBottom: 8,
};

const legendStackStyle = {
  position: "fixed",
  bottom: 16,
  left: 16,
  zIndex: 1500,
};

function LegendItem({ label, color }) {
  return (
    <div style={{ display: "flex", alignItems: "center" }}>
      <div style={{
        width: 10,
        height: 10,
        borderRadius: "50%",
        background: color,
        marginRight: 6
      }} />
      {label}
    </div>
  );
}

function LegendSpeed() {
  const items = [
    { label: "< 10 km/h", color: "#800080" },
    { label: "10–15 km/h", color: "#ff0000" },
    { label: "15–20 km/h", color: "#ff8800" },
    { label: "20–30 km/h", color: "#ffdd00" },
    { label: "> 30 km/h", color: "#00aa00" },
  ];

  return (
    <div style={legendBoxStyle}>
      <b>Velocidade média (15 min)</b>
      {items.map(i => <LegendItem key={i.label} {...i} />)}
    </div>
  );
}

function LegendComparison() {
  const items = [
    { label: "> 1.10 • Acima do esperado", color: "#006400" },
    { label: "0.95–1.10 • Dentro do esperado", color: "#00aa00" },
    { label: "0.85–0.95 • Lentidão", color: "#ffdd00" },
    { label: "0.65–0.85 • Grande lentidão", color: "#ff8800" },
    { label: "0.55–0.65 • Engarrafamento", color: "#ff0000" },
    { label: "< 0.55 • Problema viário", color: "#800080" },
    { label: "Sem histórico", color: "#cccccc" },
  ];

  return (
    <div style={legendBoxStyle}>
      <b>Comparação histórico × realtime</b>
      {items.map(i => <LegendItem key={i.label} {...i} />)}
    </div>
  );
}

function LegendStack({ showSpeed, showComparison }) {
  if (!showSpeed && !showComparison) return null;

  return (
    <div style={legendStackStyle}>
      {showSpeed && <LegendSpeed />}
      {showComparison && <LegendComparison />}
    </div>
  );
}

// ================= MAP CLICK HANDLER =================
function MapClickHandler({ clearSelections }) {
  useMapEvents({
    click: () => {
      clearSelections();
    }
  });
  return null;
}

// ================= MAP =================
export default function MapView({ setScreen }) {

  const [vehicles, setVehicles] = useState([]);
  const [subtrechos, setSubtrechos] = useState([]);
  const [subtrechosAll, setSubtrechosAll] = useState([]);
  const [subtrechosComparison, setSubtrechosComparison] = useState([]);

  const [menuOpen, setMenuOpen] = useState(false);
  const [clock, setClock] = useState("");

  const [layers, setLayers] = useState({
    vehicles: true,
    subtrechos: false,
    subtrechosAll: false,
    subtrechosComparison: false,
  });

  // ================= SELEÇÃO POR CAMADA =================
  const [selected, setSelected] = useState({
    subtrechos: null,
    subtrechosAll: null,
    subtrechosComparison: null
  });

  const clearAllSelections = () => {
    setSelected({
      subtrechos: null,
      subtrechosAll: null,
      subtrechosComparison: null
    });
  };

  // Limpa seleção quando desliga a camada
  useEffect(() => {
    setSelected(s => ({
      ...s,
      subtrechos: layers.subtrechos ? s.subtrechos : null,
      subtrechosAll: layers.subtrechosAll ? s.subtrechosAll : null,
      subtrechosComparison: layers.subtrechosComparison ? s.subtrechosComparison : null,
    }));
  }, [layers.subtrechos, layers.subtrechosAll, layers.subtrechosComparison]);

  // =========================================================
  // ✅ PADRÃO VISUAL ÚNICO PARA TRECHOS (IGUAL AO ALL)
  // =========================================================
  const fadedOpacity = 0.15;

  // estilo base igual ao ALL
  const baseOpacity = 0.6;

  // peso base = ALL
  const calcWeightByN = (n) => {
    const nn = Number(n ?? 0);
    return Math.min(8, 2 + Math.log(nn + 1) * 2);
  };

  // quando selecionado, dá um destaque consistente
  const selectedWeight = 9;
  const selectedOpacity = 0.85;

  // helpers de opacidade por camada (padronizado)
  const opacityPairs = useMemo(() => {
    return (id) => {
      if (!layers.subtrechos) return baseOpacity;
      if (!selected.subtrechos) return baseOpacity;
      return selected.subtrechos === id ? selectedOpacity : fadedOpacity;
    };
  }, [layers.subtrechos, selected.subtrechos]);

  const opacityAll = useMemo(() => {
    return (id) => {
      if (!layers.subtrechosAll) return baseOpacity;
      if (!selected.subtrechosAll) return baseOpacity;
      return selected.subtrechosAll === id ? selectedOpacity : fadedOpacity;
    };
  }, [layers.subtrechosAll, selected.subtrechosAll]);

  const opacityComparison = useMemo(() => {
    return (id) => {
      if (!layers.subtrechosComparison) return baseOpacity;
      if (!selected.subtrechosComparison) return baseOpacity;
      return selected.subtrechosComparison === id ? selectedOpacity : fadedOpacity;
    };
  }, [layers.subtrechosComparison, selected.subtrechosComparison]);

  // ===== RELÓGIO =====
  useEffect(() => {
    const t = setInterval(() => {
      setClock(new Date().toLocaleTimeString());
    }, 1000);
    return () => clearInterval(t);
  }, []);

  // ===== VEÍCULOS =====
  useEffect(() => {
    function load() {
      fetch(`${API}/map/vehicles`)
        .then(r => r.json())
        .then(setVehicles)
        .catch(console.error);
    }
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  // ===== SUBTRECHOS PAIRS =====
  useEffect(() => {
    if (!layers.subtrechos) return;

    fetch(`${API}/map/subtrechos/pairs`)
      .then(r => r.json())
      .then(setSubtrechos)
      .catch(console.error);
  }, [layers.subtrechos]);

  // ===== SUBTRECHOS ALL =====
  useEffect(() => {
    if (!layers.subtrechosAll) return;

    fetch(`${API}/map/subtrechos/all`)
      .then(r => r.json())
      .then(setSubtrechosAll)
      .catch(console.error);
  }, [layers.subtrechosAll]);

  // ===== SUBTRECHOS COMPARISON =====
  useEffect(() => {
    if (!layers.subtrechosComparison) return;

    fetch(`${API}/map/subtrechos/comparison`)
      .then(r => r.json())
      .then(fc => setSubtrechosComparison(fc.features || []))
      .catch(console.error);
  }, [layers.subtrechosComparison]);

  return (
    <>
      {/* ================= HEADER ================= */}
      <div style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        height: 50,
        background: "#35bfe6",
        color: "white",
        display: "flex",
        alignItems: "center",
        padding: "0 16px",
        zIndex: 2000
      }}>
        <div
          style={{ cursor: "pointer", fontSize: 22, marginRight: 16 }}
          onClick={() => setMenuOpen(!menuOpen)}
        >
          ☰
        </div>

        <div style={{
          flex: 1,
          height: "100%",
          overflow: "hidden",
          display: "flex",
          alignItems: "center"
        }}>
          <img
            src={logo}
            alt="URBI"
            style={{
              height: 90,
              width: "auto",
              display: "block",
              objectFit: "cover"
            }}
          />
        </div>

        <div style={{ fontFamily: "monospace" }}>
          {clock}
        </div>
      </div>

      {/* ================= DRAWER ================= */}
      <div style={{
        position: "fixed",
        top: 50,
        left: menuOpen ? 0 : -280,
        width: 260,
        height: "calc(100% - 50px)",
        background: "#ffffff",
        boxShadow: menuOpen ? "2px 0 8px rgba(0,0,0,0.25)" : "none",
        transition: "left 0.3s",
        padding: 16,
        zIndex: 1900,
        pointerEvents: menuOpen ? "auto" : "none"
      }}>

        {/* ✅ NAVEGAÇÃO ENTRE TELAS */}
        <h3>Menu</h3>

        <button
          style={{
            width: "100%",
            padding: "10px 12px",
            marginBottom: 8,
            borderRadius: 8,
            border: "1px solid #ddd",
            background: "#f7f7f7",
            cursor: "pointer",
            textAlign: "left"
          }}
          onClick={() => {
            setMenuOpen(false);
            setScreen("camadas");
          }}
        >
          🗺️ Camadas
        </button>

        <button
          style={{
            width: "100%",
            padding: "10px 12px",
            marginBottom: 14,
            borderRadius: 8,
            border: "1px solid #ddd",
            background: "#ffffff",
            cursor: "pointer",
            textAlign: "left"
          }}
          onClick={() => {
            setMenuOpen(false);
            setScreen("lista");
          }}
        >
          📋 Lista
        </button>

        <hr style={{ margin: "14px 0" }} />

        <h3>Camadas</h3>

        {Object.entries({
          vehicles: "Veículos",
          subtrechos: "Subtrechos selecionados (pairs)",
          subtrechosAll: "Velocidade global (todos os pares)",
          subtrechosComparison: "Comparação histórico × realtime"
        }).map(([k, label]) => (
          <label key={k}>
            <input
              type="checkbox"
              checked={layers[k]}
              onChange={() =>
                setLayers(l => ({ ...l, [k]: !l[k] }))
              }
            /> {label}
            <br /><br />
          </label>
        ))}
      </div>

      {/* ================= MAP ================= */}
      <div style={{
        position: "absolute",
        top: 50,
        left: 0,
        right: 0,
        bottom: 0
      }}>
        <MapContainer
          center={[-15.8, -47.9]}
          zoom={11}
          zoomControl={false}
          style={{ height: "100%", width: "100%" }}
        >
          <ZoomControl position="bottomright" />

          <MapClickHandler clearSelections={clearAllSelections} />

          <LayersControl position="topright">
            <BaseLayer checked name="Mapa claro">
              <TileLayer
                url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
                attribution="&copy; OpenStreetMap & CARTO"
              />
            </BaseLayer>

            <BaseLayer name="Mapa escuro">
              <TileLayer
                url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
                attribution="&copy; OpenStreetMap & CARTO"
              />
            </BaseLayer>

            {/* ✅ SATÉLITE (VOLTOU) */}
            <BaseLayer name="Satélite">
              <TileLayer
                url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
                attribution="Tiles &copy; Esri"
              />
            </BaseLayer>
          </LayersControl>

          {/* ===== VEÍCULOS ===== */}
          {layers.vehicles && vehicles.map(v => (
            v.lat != null && v.lon != null && (
              <Marker
                key={v.vehicle_id}
                position={[v.lat, v.lon]}
                icon={circleIcon(speedColor(v.speed_kmh))}
              >
                <Popup>
                  <b>Veículo:</b> {v.vehicle_label || v.vehicle_id}<br />
                  <b>Linha:</b> {v.route_id || "—"}<br />
                  <b>Velocidade:</b> {v.speed_kmh ?? "—"} km/h<br />
                  <b>Status:</b> {v.status}<br />
                  <b>Atualizado:</b>{" "}
                  {new Date(v.event_ts * 1000).toLocaleTimeString()}
                </Popup>
              </Marker>
            )
          ))}

          {/* ======================================================
              ✅ SUBTRECHOS PAIRS (PADRÃO ALL)
             ====================================================== */}
          {layers.subtrechos && subtrechos.map(st => (
            <Polyline
              key={`pairs-${st.subtrecho_id}`}
              positions={st.coords}
              pathOptions={{
                color: speedColor(st.speed_kmh),
                weight:
                  selected.subtrechos === st.subtrecho_id
                    ? selectedWeight
                    : calcWeightByN(st.n),
                opacity: opacityPairs(st.subtrecho_id)
              }}
              eventHandlers={{
                click: (e) => {
                  if (e?.originalEvent) e.originalEvent.stopPropagation();
                  setSelected(s => ({ ...s, subtrechos: st.subtrecho_id }));
                }
              }}
            >
              <Popup>
                <b>Trecho:</b> {st.subtrecho_id}<br />
                <b>Velocidade:</b> {st.speed_kmh} km/h<br />
                <b>Amostras:</b> {st.n}<br />
                <b>Última:</b>{" "}
                {new Date(st.last_ts * 1000).toLocaleTimeString()}
              </Popup>
            </Polyline>
          ))}

          {/* ======================================================
              ✅ SUBTRECHOS ALL (já era o padrão)
             ====================================================== */}
          {layers.subtrechosAll && subtrechosAll.map(st => (
            <Polyline
              key={`all-${st.subtrecho_id}`}
              positions={st.coords}
              pathOptions={{
                color: speedColor(st.speed_kmh),
                weight:
                  selected.subtrechosAll === st.subtrecho_id
                    ? selectedWeight
                    : calcWeightByN(st.n),
                opacity: opacityAll(st.subtrecho_id)
              }}
              eventHandlers={{
                click: (e) => {
                  if (e?.originalEvent) e.originalEvent.stopPropagation();
                  setSelected(s => ({ ...s, subtrechosAll: st.subtrecho_id }));
                }
              }}
            >
              <Popup>
                <b>Trecho:</b> {st.subtrecho_id}<br />

                <b>Velocidade média (15 min):</b> {st.speed_kmh} km/h<br />
                <b>Amostras:</b> {st.n}<br />

                {/* ===== DEBUG DO CÁLCULO REALTIME ===== */}
                {"distance_m" in st && (
                  <>
                    <hr style={{ margin: "8px 0" }} />
                    <b>Distância usada:</b>{" "}
                    {st.distance_m != null ? `${st.distance_m} m` : "—"}<br />

                    <b>Tempo usado (dt):</b>{" "}
                    {st.dt_sec != null ? `${st.dt_sec} s` : "—"}<br />

                    <b>Velocidade última amostra:</b>{" "}
                    {st.speed_last_kmh != null ? `${st.speed_last_kmh} km/h` : "—"}<br />

                    <b>t0:</b>{" "}
                    {st.t0_ts != null
                      ? new Date(st.t0_ts * 1000).toLocaleTimeString()
                      : "—"}
                    <br />

                    <b>t1:</b>{" "}
                    {st.t1_ts != null
                      ? new Date(st.t1_ts * 1000).toLocaleTimeString()
                      : "—"}
                    <br />
                  </>
                )}

                <hr style={{ margin: "8px 0" }} />
                <b>Última atualização:</b>{" "}
                {st.last_ts ? new Date(st.last_ts * 1000).toLocaleTimeString() : "—"}
              </Popup>
            </Polyline>
          ))}

          {/* ======================================================
              ✅ SUBTRECHOS COMPARISON (PADRÃO ALL)
             ====================================================== */}
          {layers.subtrechosComparison && subtrechosComparison.map((f, i) => {
            const id = `${f.properties.s1}->${f.properties.s2}`;
            const n = f.properties.n_realtime ?? f.properties.n_hist ?? 0;

            return (
              <Polyline
                key={`cmp-${i}`}
                positions={f.geometry.coordinates.map(c => [c[1], c[0]])}
                pathOptions={{
                  color: comparisonColor(f.properties.color),
                  weight:
                    selected.subtrechosComparison === id
                      ? selectedWeight
                      : calcWeightByN(n),
                  opacity: opacityComparison(id)
                }}
                eventHandlers={{
                  click: (e) => {
                    if (e?.originalEvent) e.originalEvent.stopPropagation();
                    setSelected(s => ({ ...s, subtrechosComparison: id }));
                  }
                }}
              >
                <Popup>
                  <b>Trecho:</b> {f.properties.s1} → {f.properties.s2}<br />
                  <b>Realtime:</b> {f.properties.speed_realtime_kmh ?? "—"} km/h<br />
                  <b>Histórico:</b> {f.properties.speed_hist_kmh ?? "—"} km/h<br />
                  <b>Razão:</b>{" "}
                  {f.properties.ratio != null
                    ? f.properties.ratio.toFixed(2)
                    : "—"}
                  <br />
                  <b>Confiança:</b> {f.properties.confidence ?? "—"}
                </Popup>
              </Polyline>
            );
          })}

        </MapContainer>
      </div>

      {/* ================= LEGENDS ================= */}
      <LegendStack
        showSpeed={
          layers.vehicles ||
          layers.subtrechos ||
          layers.subtrechosAll
        }
        showComparison={layers.subtrechosComparison}
      />
    </>
  );
}
