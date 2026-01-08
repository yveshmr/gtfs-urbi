import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  LayersControl,
  useMap
} from "react-leaflet";
import { useEffect, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

const { BaseLayer } = LayersControl;

const API = "http://127.0.0.1:8000";

//
// ================= ICONS =================
//

// 🔵 Bolinha SVG inline — 16x16
const circleIcon = (color = "#999") =>
  L.divIcon({
    html: `
      <svg xmlns="http://www.w3.org/2000/svg"
           width="16" height="16"
           viewBox="0 0 16 16">
        <circle
          cx="8"
          cy="8"
          r="7"
          fill="${color}"
          stroke="white"
          stroke-width="1"
        />
      </svg>
    `,
    className: "",
    iconSize: [16, 16],
    iconAnchor: [8, 8],
  });

//
// ============ COLOR SCALE FUNCTION =========
//
function speedColor(v) {
  if (v == null) return "#cccccc";
  if (v === 0) return "#cccccc";
  if (v < 10) return "#800080";
  if (v < 15) return "#ff0000";
  if (v < 20) return "#ff8800";
  if (v < 30) return "#ffdd00";
  return "#00aa00";
}

//
// ================= LEGEND CONTROL =================
//
function SpeedLegend() {
  const map = useMap();

  useEffect(() => {

    const legend = L.control({ position: "bottomleft" });

    legend.onAdd = function () {
      const div = L.DomUtil.create("div", "speed-legend");

      div.innerHTML = `
        <div style="
          background: rgba(255,255,255,0.95);
          padding: 8px 10px;
          border-radius: 4px;
          font-size: 12px;
          line-height: 18px;
          box-shadow: 0 0 6px rgba(0,0,0,0.3);
        ">
          <b>Velocidade (km/h)</b>

          <div style="display:flex;align-items:center;margin-top:4px;">
            <span style="width:10px;height:10px;border-radius:50%;
                         background:#cccccc;border:1px solid #fff;
                         display:inline-block;margin-right:6px;"></span>
            sem dado
          </div>

          <div style="display:flex;align-items:center;">
            <span style="width:10px;height:10px;border-radius:50%;
                         background:#800080;border:1px solid #fff;
                         display:inline-block;margin-right:6px;"></span>
            &lt; 10
          </div>

          <div style="display:flex;align-items:center;">
            <span style="width:10px;height:10px;border-radius:50%;
                         background:#ff0000;border:1px solid #fff;
                         display:inline-block;margin-right:6px;"></span>
            10 – 14
          </div>

          <div style="display:flex;align-items:center;">
            <span style="width:10px;height:10px;border-radius:50%;
                         background:#ff8800;border:1px solid #fff;
                         display:inline-block;margin-right:6px;"></span>
            15 – 19
          </div>

          <div style="display:flex;align-items:center;">
            <span style="width:10px;height:10px;border-radius:50%;
                         background:#ffdd00;border:1px solid #fff;
                         display:inline-block;margin-right:6px;"></span>
            20 – 29
          </div>

          <div style="display:flex;align-items:center;">
            <span style="width:10px;height:10px;border-radius:50%;
                         background:#00aa00;border:1px solid #fff;
                         display:inline-block;margin-right:6px;"></span>
            ≥ 30
          </div>
        </div>
      `;

      return div;
    };

    legend.addTo(map);
    return () => legend.remove();

  }, [map]);

  return null;
}

export default function MapView() {

  const [vehicles, setVehicles] = useState([]);

  //
  // Load vehicles periodically
  //
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

  return (
    <MapContainer
      center={[-15.8, -47.9]}
      zoom={11}
      style={{ height: "100vh", width: "100%" }}
    >

      <LayersControl position="topright">

        {/* ================= MAPA DE TRÂNSITO ================= */}
        <BaseLayer checked name="Mapa de Trânsito">
          <TileLayer
            url="https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}{r}.png"
            attribution="&copy; Stadia Maps &copy; OpenMapTiles &copy; OpenStreetMap"
          />
        </BaseLayer>

        {/* ================= SATÉLITE (SEM LABELS) ================= */}
        <BaseLayer name="Satélite">
          <TileLayer
            url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
            attribution="&copy; Esri"
          />
        </BaseLayer>

      </LayersControl>

      {/* ================= LEGENDA ================= */}
      <SpeedLegend />

      {/* ================= VEHICLES ================= */}
      {vehicles.map(v => {

        if (!v.lat || !v.lon) return null;

        const color = speedColor(v.speed_kmh);
        const icon = circleIcon(color);

        return (
          <Marker
            key={v.vehicle_id}
            position={[v.lat, v.lon]}
            icon={icon}
          >
            <Popup>
              <b>Veículo:</b> {v.vehicle_label}<br />
              <b>Linha:</b> {v.route_short_name || v.route_id || ""}<br />
              <b>Velocidade:</b> {v.speed_kmh ?? ""}<br />
              <b>Última atualização:</b> {v.last_update_ts ?? ""}
            </Popup>
          </Marker>
        );
      })}

    </MapContainer>
  );
}
