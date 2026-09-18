import { useEffect, useRef, useState } from "react";
import { MapPin, X } from "lucide-react";

type Coordinates = { latitude: number; longitude: number };

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

export function ReportLocationPicker({ value, deviceLocation, onChange, onClose }: { value: Coordinates | null; deviceLocation: Coordinates | null; onChange: (location: Coordinates) => void; onClose: () => void }) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<any>(null);
  const marker = useRef<any>(null);
  const selected = useRef<Coordinates | null>(value);
  const [displayLocation, setDisplayLocation] = useState<Coordinates | null>(value);

  useEffect(() => {
    let cancelled = false;
    void loadLeaflet().then(L => {
      if (cancelled || !container.current) return;
      const initial = value ?? deviceLocation ?? { latitude: 20.5937, longitude: 78.9629 };
      map.current = L.map(container.current, { zoomControl: true }).setView([initial.latitude, initial.longitude], value || deviceLocation ? 16 : 5);
      L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", { maxZoom: 19, attribution: "Tiles © Esri" }).addTo(map.current);
      const setPin = (location: Coordinates) => {
        selected.current = location;
        setDisplayLocation(location);
        if (!marker.current) marker.current = L.marker([location.latitude, location.longitude]).addTo(map.current);
        else marker.current.setLatLng([location.latitude, location.longitude]);
        onChange(location);
      };
      if (value) setPin(value);
      map.current.on("click", (event: any) => setPin({ latitude: event.latlng.lat, longitude: event.latlng.lng }));
    });
    return () => { cancelled = true; map.current?.remove(); map.current = null; marker.current = null; };
  }, []);

  return <section className="report-location-picker md:col-span-2" aria-label="Manual incident location picker">
    <div className="report-location-picker__head"><div><strong><MapPin size={15} />Drop a pin for this incident</strong><span>Click the exact road location on the satellite map.</span></div><button type="button" onClick={onClose} aria-label="Close location picker"><X size={16} /></button></div>
    <div ref={container} className="report-location-picker__map" />
    <p>{displayLocation ? `${displayLocation.latitude.toFixed(6)}, ${displayLocation.longitude.toFixed(6)}` : "No pin selected yet"}</p>
  </section>;
}
