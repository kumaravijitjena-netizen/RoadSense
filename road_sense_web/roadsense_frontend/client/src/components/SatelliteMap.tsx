import { useEffect, useRef, useState } from "react";

type Position = { latitude: number; longitude: number; accuracy?: number };

declare global {
  interface Window { L?: any }
}

const leafletCss = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
const leafletScript = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";

function loadLeaflet() {
  if (window.L) return Promise.resolve(window.L);
  return new Promise<any>((resolve, reject) => {
    if (!document.querySelector(`link[href="${leafletCss}"]`)) {
      const css = document.createElement("link"); css.rel = "stylesheet"; css.href = leafletCss; document.head.appendChild(css);
    }
    const script = document.createElement("script"); script.src = leafletScript; script.onload = () => resolve(window.L); script.onerror = reject; document.head.appendChild(script);
  });
}

export function SatelliteMap({ position, onPosition, incidents = [], onIncidentSelect }: { position: Position | null; onPosition: (position: Position) => void; incidents?: Array<{ id: string; latitude: number; longitude: number; type: string }>; onIncidentSelect?: (id: string) => void }) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<any>(null);
  const marker = useRef<any>(null);
  const incidentLayer = useRef<any>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let watchId: number | undefined;
    loadLeaflet().then((L) => {
      if (!container.current || map.current) return;
      map.current = L.map(container.current, { zoomControl: false, attributionControl: true }).setView([12.9716, 77.5946], 13);
      L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", { maxZoom: 19, attribution: "Tiles © Esri" }).addTo(map.current);
      L.control.zoom({ position: "bottomright" }).addTo(map.current);
      if (!navigator.geolocation) { setError("Location is not supported by this browser."); return; }
      watchId = navigator.geolocation.watchPosition(
        ({ coords }) => onPosition({ latitude: coords.latitude, longitude: coords.longitude, accuracy: coords.accuracy }),
        () => setError("Allow location access to center the satellite map on this device."),
        { enableHighAccuracy: true, maximumAge: 10000, timeout: 15000 },
      );
    }).catch(() => setError("Satellite map could not be loaded."));
    return () => { if (watchId !== undefined) navigator.geolocation.clearWatch(watchId); map.current?.remove(); map.current = null; };
  }, [onPosition]);

  useEffect(() => {
    if (!position || !map.current || !window.L) return;
    const point = [position.latitude, position.longitude];
    if (!marker.current) marker.current = window.L.circleMarker(point, { radius: 9, color: "#ffffff", weight: 2, fillColor: "#f3b84b", fillOpacity: 1 }).addTo(map.current);
    else marker.current.setLatLng(point);
    map.current.setView(point, Math.max(map.current.getZoom(), 16));
  }, [position]);

  useEffect(() => {
    if (!map.current || !window.L) return;
    incidentLayer.current?.clearLayers();
    incidentLayer.current = window.L.layerGroup().addTo(map.current);
    incidents.filter((incident) => Number.isFinite(incident.latitude) && Number.isFinite(incident.longitude)).forEach((incident) => {
      const color = incident.type.toLowerCase() === "pothole" ? "#f3b84b" : "#61d0bc";
      const marker = window.L.circleMarker([incident.latitude, incident.longitude], { radius: 8, color: "#ffffff", weight: 2, fillColor: color, fillOpacity: 1 });
      marker.bindTooltip(`${incident.type} incident`, { direction: "top" });
      if (onIncidentSelect) marker.on("click", () => onIncidentSelect(incident.id));
      marker.addTo(incidentLayer.current);
    });
  }, [incidents, onIncidentSelect]);

  return <div className="satellite-map relative h-[390px] overflow-hidden"><div ref={container} className="h-full w-full bg-[#101924]" />{error && <div className="absolute inset-x-4 bottom-4 rounded-md bg-[#0b1019]/90 px-3 py-2 text-[11px] text-slate-300 backdrop-blur">{error}</div>}</div>;
}
