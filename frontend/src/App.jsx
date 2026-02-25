import { useState } from "react";
import MapView from "./MapView";
import ListView from "./ListView";

export default function App() {
  const [screen, setScreen] = useState("camadas");

  return (
    <div style={{ height: "100vh", width: "100vw" }}>
      {screen === "camadas" && <MapView setScreen={setScreen} />}
      {screen === "lista" && <ListView setScreen={setScreen} />}
    </div>
  );
}
