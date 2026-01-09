import {
  MapContainer,
  TileLayer,
  Polyline,
  Marker,
  Popup,
  ZoomControl,
  LayersControl
} from "react-leaflet";
import { useEffect, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

const { BaseLayer } = LayersControl;
const API = "http://127.0.0.1:8000";

//
// ================= ICON =================
//
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

//
// ============ COLOR SCALE ============
//
function speedColor(v) {
  if (v == null) return "#cccccc";
  if (v < 10) return "#800080";
  if (v < 15) return "#ff0000";
  if (v < 20) return "#ff8800";
  if (v < 30) return "#ffdd00";
  return "#00aa00";
}

//
// ============ LEGEND ============
//
function Legend() {
  const items = [
    { label: "< 10 km/h", color: "#800080" },
    { label: "10–15 km/h", color: "#ff0000" },
    { label: "15–20 km/h", color: "#ff8800" },
    { label: "20–30 km/h", color: "#ffdd00" },
    { label: "> 30 km/h", color: "#00aa00" },
  ];

  return (
    <div style={{
      position: "fixed",
      bottom: 16,
      left: 16,
      background: "white",
      padding: 10,
      borderRadius: 6,
      boxShadow: "0 2px 6px rgba(0,0,0,0.3)",
      fontSize: 12,
      zIndex: 1500
    }}>
      <b>Velocidade</b>
      {items.map(i => (
        <div key={i.label} style={{ display: "flex", alignItems: "center" }}>
          <div style={{
            width: 10,
            height: 10,
            borderRadius: "50%",
            background: i.color,
            marginRight: 6
          }} />
          {i.label}
        </div>
      ))}
    </div>
  );
}

export default function MapView() {

  const [vehicles, setVehicles] = useState([]);
  const [subtrechos, setSubtrechos] = useState([]);
  const [menuOpen, setMenuOpen] = useState(false);
  const [clock, setClock] = useState("");

  const [layers, setLayers] = useState({
    vehicles: true,
    subtrechos: false,
  });

  // ===== relógio =====
  useEffect(() => {
    const t = setInterval(() => {
      setClock(new Date().toLocaleTimeString());
    }, 1000);
    return () => clearInterval(t);
  }, []);

  // ===== veículos =====
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

  // ===== subtrechos =====
  useEffect(() => {
    if (!layers.subtrechos) return;
    fetch(`${API}/map/subtrechos/shape`)
      .then(r => r.json())
      .then(setSubtrechos)
      .catch(console.error);
  }, [layers.subtrechos]);

  return (
    <>
      {/* ================= HEADER ================= */}
      <div style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        height: 50,
        background: "#0b66ff",
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

        <div style={{ fontWeight: "bold", flex: 1 }}>
          URBI • Monitoramento
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
        <h3>Camadas</h3>

        <label>
          <input
            type="checkbox"
            checked={layers.vehicles}
            onChange={() =>
              setLayers(l => ({ ...l, vehicles: !l.vehicles }))
            }
          /> Velocidade dos veículos
        </label>

        <br />

        <label>
          <input
            type="checkbox"
            checked={layers.subtrechos}
            onChange={() =>
              setLayers(l => ({ ...l, subtrechos: !l.subtrechos }))
            }
          /> Velocidade dos trechos (shape)
        </label>
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

          {/* 🔽 ÚNICA PARTE ALTERADA 🔽 */}
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

            <BaseLayer name="Satélite">
              <TileLayer
                url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
                attribution="Tiles © Esri"
              />
            </BaseLayer>

          </LayersControl>

          {layers.subtrechos && subtrechos.map(st => (
            <Polyline
              key={st.subtrecho_id}
              positions={st.coords}
              pathOptions={{
                color: speedColor(st.speed_kmh),
                weight: 6,
                opacity: 0.9
              }}
            />
          ))}

          {layers.vehicles && vehicles.map(v => {
            if (!v.lat || !v.lon) return null;
            return (
              <Marker
                key={v.vehicle_id}
                position={[v.lat, v.lon]}
                icon={circleIcon(speedColor(v.speed_kmh))}
              />
            );
          })}
        </MapContainer>
      </div>

      <Legend />
    </>
  );
}
