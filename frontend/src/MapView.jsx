import { MapContainer, TileLayer, Polyline, Marker, Popup } from "react-leaflet";
import { useEffect, useState } from "react";
import "leaflet/dist/leaflet.css";

const API = "http://127.0.0.1:8000";

export default function MapView() {

  const [shapes, setShapes] = useState({});
  const [vehicles, setVehicles] = useState([]);

  //
  // Load shapes once
  //
  useEffect(() => {
    fetch(`${API}/map/shapes`)
      .then(r => r.json())
      .then(data => setShapes(data))
      .catch(err => console.error("Erro shapes:", err));
  }, []);

  //
  // Load vehicles periodically
  //
  useEffect(() => {

    function load() {
      fetch(`${API}/map/vehicles`)
        .then(r => r.json())
        .then(data => setVehicles(data))
        .catch(err => console.error("Erro vehicles:", err));
    }

    load();
    const id = setInterval(load, 5000);

    return () => clearInterval(id);
  }, []);

  return (
    <MapContainer
      center={[-15.8, -47.9]}
      zoom={11}
      style={{ height: "100%", width: "100%" }}
    >
      <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />

      {Object.entries(shapes).map(([id, coords]) => (
        <Polyline
          key={id}
          positions={coords}
          pathOptions={{ color: "#0b66ff", weight: 3 }}
        />
      ))}

      {vehicles.map(v =>
        (v.lat && v.lon) ? (
          <Marker key={v.vehicle_id} position={[v.lat, v.lon]}>
            <Popup>
              <b>Linha:</b> {v.route_short_name || v.route_id}<br />
              <b>Veículo:</b> {v.vehicle_label}<br />
              <b>Status:</b> {v.status}
            </Popup>
          </Marker>
        ) : null
      )}

    </MapContainer>
  );
}
