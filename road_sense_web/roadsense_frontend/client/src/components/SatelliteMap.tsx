import { useEffect, useRef, useState } from "react";
import { Maximize2, Minimize2 } from "lucide-react";

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

type MapIncident = {
  id: string;
  latitude: number | null;
  longitude: number | null;
  type: string;
  location: string;
  evidenceUrl?: string;
  evidenceKind?: "image" | "video";
};

type MapZone = {
  zone_key: string;
  latitude: number;
  longitude: number;
  count: number;
  color: "green" | "blue" | "yellow" | "orange" | "red";
};

const zoneColors: Record<MapZone["color"], string> = { green: "#50c896", blue: "#5f94ff", yellow: "#f4cf58", orange: "#f58b3a", red: "#ef5a62" };

function incidentPopup(incident: MapIncident, hasCoordinates: boolean) {
  const popup = document.createElement("div");
  popup.className = "roadsense-map-popup";
  const title = document.createElement("strong");
  title.textContent = incident.type;
  const location = document.createElement("p");
  location.textContent = hasCoordinates ? incident.location : `${incident.location} (GPS not supplied)`;
  popup.append(title, location);
  if (incident.evidenceUrl && incident.evidenceKind === "image") {
    const image = document.createElement("img");
    image.src = incident.evidenceUrl;
    image.alt = `${incident.type} report evidence`;
    image.loading = "lazy";
    popup.append(image);
  } else if (incident.evidenceUrl && incident.evidenceKind === "video") {
    const video = document.createElement("video");
    video.src = incident.evidenceUrl;
    video.controls = true;
    video.preload = "metadata";
    popup.append(video);
  }
  return popup;
}

export function SatelliteMap({ position, onPosition, incidents = [], zones = [], selectedId, onIncidentSelect }: { position: Position | null; onPosition: (position: Position) => void; incidents?: MapIncident[]; zones?: MapZone[]; selectedId?: string; onIncidentSelect?: (id: string) => void }) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<any>(null);
  const marker = useRef<any>(null);
  const incidentLayer = useRef<any>(null);
  const zoneLayer = useRef<any>(null);
  const incidentMarkers = useRef(new Map<string, any>());
  const [error, setError] = useState("");
  const [fullscreen, setFullscreen] = useState(false);

  useEffect(() => {
    let watchId: number | undefined;
    loadLeaflet().then((L) => {
      if (!container.current || map.current) return;
      map.current = L.map(container.current, { zoomControl: false, attributionControl: true }).setView([20.5937, 78.9629], 5);
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
    incidentMarkers.current.clear();
    incidentLayer.current = window.L.layerGroup().addTo(map.current);
    incidents.forEach(incident => {
      const hasCoordinates = Number.isFinite(incident.latitude) && Number.isFinite(incident.longitude);
      // Do not invent a map position for a report whose original file has no GPS.
      if (!hasCoordinates) return;
      const point: [number, number] = [incident.latitude as number, incident.longitude as number];
      const color = incident.type.toLowerCase() === "pothole" ? "#f3b84b" : "#61d0bc";
      const marker = window.L.circleMarker(point, { radius: 8, color: "#ffffff", weight: 2, fillColor: color, fillOpacity: 1 });
      marker.bindTooltip(`${incident.type} incident`, { direction: "top" });
      marker.bindPopup(incidentPopup(incident, hasCoordinates), { maxWidth: 270, minWidth: 210 });
      if (onIncidentSelect) marker.on("click", () => onIncidentSelect(incident.id));
      marker.addTo(incidentLayer.current);
      incidentMarkers.current.set(incident.id, marker);
    });
  }, [incidents, onIncidentSelect]);

  useEffect(() => {
    if (!map.current || !window.L) return;
    zoneLayer.current?.clearLayers();
    zoneLayer.current = window.L.layerGroup().addTo(map.current);
    zones.forEach(zone => {
      const color = zoneColors[zone.color];
      const circle = window.L.circle([zone.latitude, zone.longitude], { radius: 850, color, weight: 2, fillColor: color, fillOpacity: .16, interactive: false });
      circle.bindTooltip(`${zone.color.toUpperCase()} zone · ${zone.count} reports`, { sticky: true });
      circle.addTo(zoneLayer.current);
    });
  }, [zones]);

  useEffect(() => {
    const selected = selectedId ? incidentMarkers.current.get(selectedId) : null;
    if (!selected || !map.current) return;
    map.current.flyTo(selected.getLatLng(), Math.max(map.current.getZoom(), 16), { duration: 0.55 });
    selected.openPopup();
  }, [selectedId, incidents]);

  const toggleFullscreen = async () => {
    const element = container.current?.parentElement;
    if (!element) return;
    if (document.fullscreenElement) await document.exitFullscreen();
    else await element.requestFullscreen();
    window.setTimeout(() => map.current?.invalidateSize(), 150);
  };

  useEffect(() => {
    const onChange = () => { setFullscreen(Boolean(document.fullscreenElement)); window.setTimeout(() => map.current?.invalidateSize(), 80); };
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  return <div className={`satellite-map relative h-[390px] overflow-hidden ${fullscreen ? "is-fullscreen" : ""}`}><div ref={container} className="h-full w-full bg-[#101924]" /><button type="button" className="satellite-map__fullscreen" onClick={() => void toggleFullscreen()} aria-label={fullscreen ? "Exit full screen map" : "Open full screen map"}>{fullscreen ? <Minimize2 size={17} /> : <Maximize2 size={17} />}</button>{error && <div className="absolute inset-x-4 bottom-4 rounded-md bg-[#0b1019]/90 px-3 py-2 text-[11px] text-slate-300 backdrop-blur">{error}</div>}</div>;
}
