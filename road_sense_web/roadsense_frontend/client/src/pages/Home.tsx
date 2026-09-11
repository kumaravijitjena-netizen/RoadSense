import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Link } from "wouter";
import { DecryptedText } from "@/components/DecryptedText";
import { DotGrid } from "@/components/DotGrid";
import { SatelliteMap } from "@/components/SatelliteMap";
import { roadsenseApi, type BackendIncident, type StreamStatus } from "@/lib/roadsense-api";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  Camera,
  Check,
  ChevronDown,
  CircleHelp,
  Crosshair,
  Gauge,
  Layers3,
  LocateFixed,
  MapPin,
  MoreHorizontal,
  Navigation,
  Radio,
  Route,
  Search,
  Send,
  Settings2,
  Siren,
  SlidersHorizontal,
  Signal,
  Square,
  Target,
  TriangleAlert,
  Video,
  Wifi,
  X,
} from "lucide-react";

type IncidentStatus = "open" | "acknowledged" | "resolved";
type Incident = {
  id: string;
  type: string;
  confidence: number;
  location: string;
  source: string;
  time: string;
  status: IncidentStatus;
  color: "orange" | "teal";
};

const initialIncidents: Incident[] = [
  { id: "RS-84A1", type: "Pothole", confidence: 96, location: "12th Main · HSR Layout", source: "vehicle-12", time: "00:42 ago", status: "open", color: "orange" },
  { id: "RS-83FC", type: "Manhole", confidence: 91, location: "27th Cross · Koramangala", source: "vehicle-08", time: "04:18 ago", status: "acknowledged", color: "teal" },
  { id: "RS-83D2", type: "Pothole", confidence: 88, location: "Outer Ring Road · Bellandur", source: "camera-04", time: "11:07 ago", status: "open", color: "orange" },
  { id: "RS-82E0", type: "Pothole", confidence: 84, location: "80 Feet Road · Indiranagar", source: "vehicle-03", time: "18:32 ago", status: "resolved", color: "orange" },
];

const routes = [
  { name: "vehicle-12", area: "South East Zone", distance: "8.4 km", status: "Live", color: "orange" },
  { name: "vehicle-08", area: "Central Zone", distance: "5.1 km", status: "Live", color: "teal" },
  { name: "camera-04", area: "East Ring", distance: "—", status: "Standby", color: "muted" },
];

function toIncident(item: BackendIncident): Incident {
  const type = item.hazard_type.charAt(0).toUpperCase() + item.hazard_type.slice(1);
  const location = item.location_name || (item.latitude === null ? "Location not supplied" : `${item.latitude.toFixed(5)}°, ${item.longitude?.toFixed(5)}°`);
  return { id: item.id, type, confidence: Math.round(item.confidence * 100), location, source: item.source_id, time: new Date(item.created_at).toLocaleString(), status: item.status === "false_positive" ? "resolved" : item.status, color: item.hazard_type === "pothole" ? "orange" : "teal" };
}

function IconButton({ label, children, onClick }: { label: string; children: React.ReactNode; onClick?: () => void }) {
  return <button aria-label={label} onClick={onClick} className="grid h-9 w-9 place-items-center rounded-lg text-slate-400 transition hover:bg-white/[.07] hover:text-slate-100 active:scale-95">{children}</button>;
}

function StatCard({ icon: Icon, label, value, detail, accent }: { icon: React.ElementType; label: string; value: string; detail: string; accent: "orange" | "teal" | "blue" }) {
  const colors = { orange: "text-[#f3b84b] bg-[#f3b84b]/10", teal: "text-[#61d0bc] bg-[#61d0bc]/10", blue: "text-[#84a7ff] bg-[#84a7ff]/10" };
  return <div className="panel-soft rounded-2xl px-4 py-4 transition hover:-translate-y-0.5 hover:bg-white/[.06]">
    <div className="mb-3 flex items-center justify-between"><span className={`grid h-8 w-8 place-items-center rounded-lg ${colors[accent]}`}><Icon size={16} /></span><span className="text-[10px] uppercase tracking-[.16em] text-slate-500">Live</span></div>
    <div className="font-display text-[25px] font-semibold tracking-[-.04em] text-slate-100">{value}</div>
    <div className="mt-1 flex items-center justify-between gap-2"><span className="text-xs text-slate-400">{label}</span><span className="text-[11px] text-slate-500">{detail}</span></div>
  </div>;
}

function StatusPill({ status }: { status: IncidentStatus }) {
  const style = status === "open" ? "bg-[#f3b84b]/10 text-[#f3b84b]" : status === "acknowledged" ? "bg-[#84a7ff]/10 text-[#9bb7ff]" : "bg-[#61d0bc]/10 text-[#61d0bc]";
  return <span className={`rounded-full px-2 py-1 text-[10px] font-semibold uppercase tracking-[.12em] ${style}`}>{status}</span>;
}

function MapPanel({ incidents, onSelect }: { incidents: Incident[]; selectedId: string; onSelect: (id: string) => void; onAcknowledge: (id: string) => void; onResolve: (id: string) => void }) {
  const [position, setPosition] = useState<{ latitude: number; longitude: number; accuracy?: number } | null>(null);
  const updatePosition = useCallback((next: { latitude: number; longitude: number; accuracy?: number }) => {
    setPosition(next);
    void roadsenseApi.postLocation({ source_id: "dashboard-device", latitude: next.latitude, longitude: next.longitude, accuracy_m: next.accuracy }).catch(() => undefined);
  }, []);
  const mappedIncidents = incidents.filter((incident) => incident.location !== "Device location pending").map((incident) => ({ id: incident.id, latitude: Number(incident.location.split("°")[0]), longitude: Number(incident.location.split(", ")[1]?.replace("°", "")), type: incident.type }));
  return <div className="map-panel panel overflow-hidden rounded-2xl"><div className="map-header flex items-center justify-between px-5 py-4"><div><div className="flex items-center gap-2"><MapPin size={15} className="text-[#61d0bc]" /><h2 className="font-display text-[15px] font-semibold text-slate-100">Detection map</h2></div><p className="mt-1 text-xs text-slate-500">Satellite imagery with device and incident locations</p></div><span className="text-[10px] font-semibold uppercase tracking-[.12em] text-[#61d0bc]">Live GPS</span></div><SatelliteMap position={position} onPosition={updatePosition} incidents={mappedIncidents} onIncidentSelect={onSelect} /></div>;
}

function SignalHero() {
  return <section className="signal-hero" aria-label="RoadSense live signal overview">
    <div className="signal-hero__wash" /><DotGrid className="signal-hero__dots" /><div className="signal-hero__grid" /><div className="signal-hero__orb signal-hero__orb--one" /><div className="signal-hero__orb signal-hero__orb--two" />
    <div className="signal-hero__content"><div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[.22em] text-white/70"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" />City signal, live</div><h2 className="signal-hero__title"><DecryptedText className="hero-decrypted" text="The road is" speed={62} startDelay={180} /><br /><em><DecryptedText className="hero-decrypted" text="speaking." speed={62} startDelay={620} /></em></h2><p className="signal-hero__copy">Live road intelligence, organized for faster response.</p></div>
  </section>;
}

function MottoRails() {
  const motto = Array.from({ length: 24 }, () => "The road is speaking. -").join(" ");
  return <div className="page-motto" aria-hidden="true"><div className="page-motto__rail page-motto__rail--left"><span>{motto}</span><span>{motto}</span></div><div className="page-motto__rail page-motto__rail--right"><span>{motto}</span><span>{motto}</span></div></div>;
}

function AppHeader() {
  return <header className="flex items-center justify-between border-b border-white/[.07] px-5 py-4 lg:px-8"><div className="flex items-center gap-3"><div className="grid h-9 w-9 place-items-center rounded-xl bg-[#f3b84b] text-[#19202b] shadow-[0_0_28px_rgba(243,184,75,.24)]"><Crosshair size={19} strokeWidth={2.5} /></div><div><div className="font-display text-[17px] font-bold tracking-[-.03em] text-slate-100">RoadSense<span className="text-[#f3b84b]">.</span></div><div className="text-[10px] font-semibold uppercase tracking-[.19em] text-slate-500">Operations control</div></div></div><Link href="/sign-in" aria-label="Open account" className="grid h-9 w-9 place-items-center rounded-full border border-white/10 bg-[#283449] text-xs font-bold text-slate-200 transition hover:bg-white hover:text-[#0b1019]">AK</Link></header>;
}

function Dock({ activeNav, onNavigate }: { activeNav: string; onNavigate: (name: string) => void }) {
  const items = [{ name: "Overview", icon: Gauge }, { name: "Live", icon: Video }, { name: "Incidents", icon: TriangleAlert }, { name: "Routes", icon: Route }];
  return <div className="dock" aria-label="Quick navigation"><div className="dock__signal" />{items.map(({ name, icon: Icon }) => <button key={name} onClick={() => { const target = name === "Live" ? "live" : name === "Incidents" ? "incidents" : name === "Routes" ? "routes" : "overview"; document.getElementById(target)?.scrollIntoView({ behavior: "smooth", block: "start" }); onNavigate(name === "Live" ? "Live streams" : name === "Routes" ? "Route history" : name); }} className={activeNav === (name === "Live" ? "Live streams" : name === "Routes" ? "Route history" : name) ? "is-active" : ""}><Icon size={15} /><span>{name}</span></button>)}</div>;
}

function OperationsTools({ onReported }: { onReported: (incident: Incident) => void }) {
  const [stream, setStream] = useState<StreamStatus>({ running: false, source_id: null, fps: 0, error: null });
  const [usingDeviceCamera, setUsingDeviceCamera] = useState(false);
  const [detectionCount, setDetectionCount] = useState(0);
  const [detections, setDetections] = useState<Array<{ class: string; confidence: number; box: number[] }>>([]);
  const [frameSize, setFrameSize] = useState({ width: 0, height: 0 });
  const [cameras, setCameras] = useState<MediaDeviceInfo[]>([]);
  const [cameraId, setCameraId] = useState("");
  const [position, setPosition] = useState<{ latitude: number; longitude: number; accuracy?: number } | null>(null);
  const [hazard, setHazard] = useState<"pothole" | "manhole" | "other">("pothole");
  const [details, setDetails] = useState("");
  const [evidence, setEvidence] = useState<File | null>(null);
  const [reporterName, setReporterName] = useState("");
  const [reporterEmail, setReporterEmail] = useState("");
  const [locationName, setLocationName] = useState("");
  const [reporting, setReporting] = useState(false);
  const [locating, setLocating] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const deviceStreamRef = useRef<MediaStream | null>(null);
  const detectionTimerRef = useRef<number | null>(null);
  const analyzingRef = useRef(false);

  const loadCameras = useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return [];
    const available = (await navigator.mediaDevices.enumerateDevices()).filter((device) => device.kind === "videoinput");
    setCameras(available);
    setCameraId((current) => {
      if (current && available.some((device) => device.deviceId === current)) return current;
      // Linked phones commonly become the Windows default. Prefer a physical webcam when one is available.
      return available.find((device) => !/(oneplus|phone|android|continuity|droidcam|iriun)/i.test(device.label))?.deviceId ?? available[0]?.deviceId ?? "";
    });
    return available;
  }, []);

  useEffect(() => {
    void roadsenseApi.streamStatus().then((status) => setStream(status.running ? status : { ...status, error: null })).catch(() => setStream((current) => ({ ...current, error: "Backend unavailable" })));
    void loadCameras();
    return () => {
      if (detectionTimerRef.current !== null) window.clearInterval(detectionTimerRef.current);
      deviceStreamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, [loadCameras]);
  useEffect(() => {
    const video = videoRef.current;
    if (!usingDeviceCamera || !video || !deviceStreamRef.current) return;
    video.srcObject = deviceStreamRef.current;
    void video.play().catch(() => setStream((current) => ({ ...current, running: false, error: "Camera preview could not start" })));
  }, [usingDeviceCamera]);
  useEffect(() => {
    const video = videoRef.current;
    const container = video?.parentElement;
    if (!usingDeviceCamera || !video || !container || !frameSize.width || !frameSize.height) return;
    const canvas = document.createElement("canvas");
    canvas.className = "detection-overlay";
    container.appendChild(canvas);
    const draw = () => {
      const bounds = container.getBoundingClientRect();
      const pixelRatio = window.devicePixelRatio || 1;
      canvas.width = Math.round(bounds.width * pixelRatio); canvas.height = Math.round(bounds.height * pixelRatio);
      canvas.style.width = `${bounds.width}px`; canvas.style.height = `${bounds.height}px`;
      const context = canvas.getContext("2d");
      if (!context) return;
      context.scale(pixelRatio, pixelRatio);
      const scale = Math.min(bounds.width / frameSize.width, bounds.height / frameSize.height);
      const renderedWidth = frameSize.width * scale, renderedHeight = frameSize.height * scale;
      const offsetX = (bounds.width - renderedWidth) / 2, offsetY = (bounds.height - renderedHeight) / 2;
      detections.forEach((detection) => {
        const [x1, y1, x2, y2] = detection.box;
        const color = detection.class.toLowerCase() === "pothole" ? "#f4b942" : "#61d0bc";
        const x = offsetX + x1 * scale, y = offsetY + y1 * scale, width = (x2 - x1) * scale, height = (y2 - y1) * scale;
        context.strokeStyle = color; context.lineWidth = 3; context.strokeRect(x, y, width, height);
        const label = `${detection.class} ${Math.round(detection.confidence * 100)}%`;
        context.font = "600 12px DM Sans, sans-serif";
        const labelWidth = context.measureText(label).width + 14;
        context.fillStyle = color; context.fillRect(x, Math.max(offsetY, y - 25), labelWidth, 21);
        context.fillStyle = "#101924"; context.fillText(label, x + 7, Math.max(offsetY + 15, y - 10));
      });
    };
    draw();
    const observer = new ResizeObserver(draw); observer.observe(container);
    return () => { observer.disconnect(); canvas.remove(); };
  }, [detections, frameSize, usingDeviceCamera]);
  const updatePosition = useCallback((next: { latitude: number; longitude: number; accuracy?: number }) => {
    setPosition(next);
    void roadsenseApi.postLocation({ source_id: "dashboard-device", latitude: next.latitude, longitude: next.longitude, accuracy_m: next.accuracy }).catch(() => undefined);
  }, []);
  const requestPosition = () => new Promise<{ latitude: number; longitude: number; accuracy?: number }>((resolve, reject) => {
    if (!navigator.geolocation) { reject(new Error("Location is not supported by this browser.")); return; }
    navigator.geolocation.getCurrentPosition(
      (current) => {
        const next = { latitude: current.coords.latitude, longitude: current.coords.longitude, accuracy: current.coords.accuracy };
        updatePosition(next);
        resolve(next);
      },
      () => reject(new Error("Allow device location to report an incident.")),
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 10_000 },
    );
  });
  const locate = async () => {
    setLocating(true);
    try { await requestPosition(); toast.success("Location ready"); }
    catch (error) { toast.error("Location unavailable", { description: error instanceof Error ? error.message : "Allow device location and try again." }); }
    finally { setLocating(false); }
  };
  const stopDeviceCamera = () => {
    if (detectionTimerRef.current !== null) window.clearInterval(detectionTimerRef.current);
    detectionTimerRef.current = null;
    deviceStreamRef.current?.getTracks().forEach((track) => track.stop());
    deviceStreamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setUsingDeviceCamera(false); setDetectionCount(0); setDetections([]); setStream({ running: false, source_id: null, fps: 0, error: null });
  };
  const analyzeDeviceFrame = async () => {
    const video = videoRef.current;
    if (!video || video.videoWidth === 0 || analyzingRef.current) return;
    analyzingRef.current = true;
    try {
      const canvas = document.createElement("canvas");
      const scale = Math.min(1, 640 / video.videoWidth);
      canvas.width = Math.max(1, Math.round(video.videoWidth * scale)); canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
      canvas.getContext("2d")?.drawImage(video, 0, 0, canvas.width, canvas.height);
      const frame = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.78));
      if (!frame) return;
      const result = await roadsenseApi.analyzeBrowserFrame(frame, position ?? undefined);
      setDetectionCount(result.count);
      setDetections(result.detections);
      setFrameSize({ width: result.frame_width, height: result.frame_height });
      result.incidents.forEach((incident) => onReported(toIncident(incident)));
      if (result.incidents.length) {
        toast.success(`${result.incidents.length} road hazard${result.incidents.length === 1 ? "" : "s"} reported`);
      }
    } catch (error) {
      setStream((current) => ({ ...current, error: error instanceof Error ? error.message : "Detection service unavailable" }));
    } finally { analyzingRef.current = false; }
  };
  const toggleStream = async () => {
    try {
      if (usingDeviceCamera) { stopDeviceCamera(); toast.success("Live camera stopped"); return; }
      if (!navigator.mediaDevices?.getUserMedia) throw new Error("This browser does not support camera access.");
      const available = await loadCameras();
      const selectedCamera = cameraId || available.find((device) => !/(oneplus|phone|android|continuity|droidcam|iriun)/i.test(device.label))?.deviceId;
      const deviceStream = await navigator.mediaDevices.getUserMedia({ video: selectedCamera ? { deviceId: { exact: selectedCamera } } : true, audio: false });
      deviceStreamRef.current = deviceStream;
      void loadCameras();
      setStream({ running: true, source_id: "browser-camera", fps: 0, error: null, model: "v2" }); setUsingDeviceCamera(true);
      void analyzeDeviceFrame();
      detectionTimerRef.current = window.setInterval(() => void analyzeDeviceFrame(), 1500);
      toast.success("Device camera connected");
    } catch (error) {
      const message = error instanceof DOMException && error.name === "NotAllowedError"
        ? "Camera permission was denied. Enable Camera for 127.0.0.1:3000 in this browser, then try again."
        : error instanceof DOMException && error.name === "NotFoundError"
          ? "No camera was found. Connect a camera, then try again."
          : error instanceof Error ? error.message : "Check camera access and backend status.";
      setStream((current) => ({ ...current, running: false, error: message }));
      toast.error("Camera could not start", { description: message });
    }
  };
  const report = async () => {
    if (!reporterName.trim() || !locationName.trim()) { toast.error("Name and location are required"); return; }
    setReporting(true);
    try {
      onReported(toIncident(await roadsenseApi.reportIncidentWithPhoto({ hazard_type: hazard, reporter_name: reporterName.trim(), reporter_email: reporterEmail.trim() || undefined, location_name: locationName.trim(), latitude: position?.latitude, longitude: position?.longitude, details, photo: evidence })));
      setDetails(""); setEvidence(null); setLocationName(""); toast.success("Incident reported", { description: "It has been added to the response queue." });
    } catch (error) { toast.error("Report could not be saved", { description: error instanceof Error ? error.message : "Check your location and try again." }); }
    finally { setReporting(false); }
  };

  return <section id="real-live-feed" className="mx-auto mt-6 max-w-[1380px] px-4 pb-2 sm:px-6 lg:px-8"><div><section className="panel overflow-hidden rounded-2xl"><div className="live-camera-heading flex items-center justify-between gap-3 border-b border-white/[.07] px-5 py-4"><div><div className="flex items-center gap-2"><Camera size={16} className="text-[#f3b84b]" /><h2 className="font-display text-[15px] font-semibold">Live camera</h2></div><p className="mt-1 text-xs text-slate-500">Your device camera with real-time RoadSense detection</p></div><div className="flex items-center gap-2">{cameras.length > 1 && <select aria-label="Select camera" value={cameraId} disabled={stream.running} onChange={(event) => setCameraId(event.target.value)} className="max-w-44 rounded-lg border border-white/10 bg-black/20 px-2 py-2 text-[10px] text-slate-200 disabled:opacity-50">{cameras.map((camera, index) => <option key={camera.deviceId} value={camera.deviceId}>{camera.label || `Camera ${index + 1}`}</option>)}</select>}<button onClick={() => void toggleStream()} className={`live-camera-toggle flex items-center gap-2 rounded-lg px-3 py-2 text-[10px] font-bold ${stream.running ? "bg-[#f3b84b] text-[#17202a]" : "border border-white/10 bg-white/[.06] text-slate-200"}`}>{stream.running ? <Square size={12} fill="currentColor" /> : <Radio size={13} />}{stream.running ? "Stop" : "Start camera"}</button></div></div><div className="live-camera-frame relative aspect-video bg-[#0a111a]">{usingDeviceCamera ? <video ref={videoRef} autoPlay muted playsInline className="h-full w-full object-contain" /> : <div className="grid h-full place-items-center text-center text-slate-500"><div><Camera size={24} className="mx-auto" /><p className="mt-3 text-xs">Camera is ready when you are.</p></div></div>}<span className="absolute right-4 top-4 rounded-md border border-white/10 bg-black/40 px-2 py-1 text-[10px] text-slate-300">{stream.running ? `${detectionCount} detections` : stream.error ?? "Standby"}</span></div></section><section className="panel mt-5 rounded-2xl p-5"><div><div className="flex items-center gap-2"><AlertTriangle size={16} className="text-[#f3b84b]" /><h2 className="font-display text-[15px] font-semibold">Report an incident</h2></div><p className="mt-1 text-xs text-slate-500">Add the reporter and location details for this incident.</p></div><div className="report-form-grid mt-4 grid gap-2 md:grid-cols-2"><input value={reporterName} onChange={(event) => setReporterName(event.target.value)} placeholder="Your name" className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-slate-200 placeholder:text-slate-600" /><input value={reporterEmail} onChange={(event) => setReporterEmail(event.target.value)} type="email" placeholder="Your email (optional)" className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-slate-200 placeholder:text-slate-600" /><input value={locationName} onChange={(event) => setLocationName(event.target.value)} placeholder="Location or address" className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-slate-200 placeholder:text-slate-600 md:col-span-2" /><select value={hazard} onChange={(event) => setHazard(event.target.value as typeof hazard)} className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-slate-200"><option value="pothole">Pothole</option><option value="manhole">Manhole</option><option value="other">Other hazard</option></select><button type="button" disabled={locating} onClick={() => void locate()} className={`flex items-center justify-center gap-2 rounded-lg border px-3 py-2 text-xs font-semibold disabled:opacity-50 ${position ? "border-[#61d0bc]/40 bg-[#61d0bc]/10 text-[#8de2d3]" : "border-white/10 text-slate-300 hover:bg-white/[.05]"}`}><MapPin size={13} />{position ? "GPS attached" : locating ? "Locating" : "Add GPS (optional)"}</button><input value={details} onChange={(event) => setDetails(event.target.value)} placeholder="Description (optional)" className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-slate-200 placeholder:text-slate-600 md:col-span-2" /><label className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-white/20 px-3 py-2 text-xs text-slate-300 hover:bg-white/[.05]"><Camera size={13} />{evidence ? evidence.name : "Add photo or video"}<input type="file" accept="image/jpeg,image/png,image/webp,video/mp4,video/webm,video/quicktime" onChange={(event) => setEvidence(event.target.files?.[0] ?? null)} className="hidden" /></label><button disabled={reporting} onClick={() => void report()} className="flex items-center justify-center gap-2 rounded-lg bg-[#f3b84b] px-4 py-2 text-xs font-bold text-[#17202a] disabled:opacity-50"><Send size={13} />{reporting ? "Sending" : "Submit report"}</button></div></section></div></section>;
}

export default function Home() {
  const [incidents, setIncidents] = useState(initialIncidents);
  const [selected, setSelected] = useState("RS-84A1");
  const [activeNav, setActiveNav] = useState("Overview");
  const [search, setSearch] = useState("");

  useEffect(() => {
    const revealObserver = new IntersectionObserver((entries) => entries.forEach((entry) => entry.isIntersecting && entry.target.classList.add("is-visible")), { threshold: 0.12 });
    document.querySelectorAll("[data-reveal]").forEach((element) => revealObserver.observe(element));
    void roadsenseApi.incidents().then((items) => { if (items.length) { const next = items.map(toIncident); setIncidents(next); setSelected(next[0].id); } }).catch(() => undefined);
    const socket = new WebSocket(roadsenseApi.socketUrl());
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data) as { event: string; data: BackendIncident };
      if (message.event === "incident" || message.event === "incident_updated") {
        const incident = toIncident(message.data);
        setIncidents((items) => [incident, ...items.filter((item) => item.id !== incident.id)]);
      }
    };
    return () => { revealObserver.disconnect(); socket.close(); };
  }, []);

  const filteredIncidents = useMemo(() => incidents.filter((item) => `${item.id} ${item.type} ${item.location} ${item.source}`.toLowerCase().includes(search.toLowerCase())), [incidents, search]);
  const selectedIncident = incidents.find((item) => item.id === selected) ?? incidents[0];
  const openCount = incidents.filter((i) => i.status === "open").length;

  const acknowledge = async (id: string) => {
    try { const saved = toIncident(await roadsenseApi.updateIncident(id, { status: "acknowledged" })); setIncidents((items) => items.map((item) => item.id === id ? saved : item)); toast.success("Incident acknowledged"); }
    catch { toast.error("Could not acknowledge this incident"); }
  };
  const resolve = async (id: string) => {
    try { const saved = toIncident(await roadsenseApi.updateIncident(id, { status: "resolved" })); setIncidents((items) => items.map((item) => item.id === id ? saved : item)); toast.success("Incident marked resolved"); }
    catch { toast.error("Could not resolve this incident"); }
  };
  const refresh = async () => { try { const items = await roadsenseApi.incidents(); if (items.length) setIncidents(items.map(toIncident)); toast.success("Dashboard refreshed"); } catch { toast.error("Backend is unavailable"); } };
  const reportIncident = (incident: Incident) => { setIncidents((items) => [incident, ...items.filter((item) => item.id !== incident.id)]); setSelected(incident.id); };

  return <div className="noise min-h-screen bg-[#0b1019] text-slate-100">
    <AppHeader />
    <DotGrid className="page-dot-grid" dotSize={2} gap={26} proximity={0} />
    <MottoRails />
    <SignalHero />
    <Dock activeNav={activeNav} onNavigate={(name) => { setActiveNav(name); toast(name, { description: ` view selected.` }); }} />
    <div className="flex">
    <main className="min-w-0 px-4 py-5 sm:px-6 lg:px-8 lg:py-7"><div className="mx-auto max-w-[1450px]">
        <div id="overview" data-reveal className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><div className="mb-2 flex items-center gap-2 text-[11px] font-bold uppercase tracking-[.18em] text-[#61d0bc]"><span className="h-1.5 w-1.5 rounded-full bg-[#61d0bc]" />Live overview</div><h1 className="font-display text-3xl font-semibold tracking-[-.055em] text-slate-100 sm:text-[38px]">See the road ahead.</h1></div></div>

        <OperationsTools onReported={reportIncident} />

        <div id="incidents" data-reveal className="mt-12"><div className="chapter-rule mb-4"><strong>03</strong> Reported incidents</div><section className="panel overflow-hidden rounded-2xl"><div className="border-b border-white/[.07] px-5 py-4"><div className="flex items-center gap-2"><Siren size={16} className="text-[#f3b84b]" /><h2 className="font-display text-[15px] font-semibold">Incidents reported</h2></div></div><div className="divide-y divide-white/[.06]">{incidents.map((incident) => <div key={incident.id} className="flex items-center gap-3 px-5 py-3.5"><div className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl ${incident.color === "orange" ? "bg-[#f3b84b]/10 text-[#f3b84b]" : "bg-[#61d0bc]/10 text-[#61d0bc]"}`}>{incident.type === "Pothole" ? <AlertTriangle size={17} /> : <CircleHelp size={17} />}</div><div className="min-w-0 flex-1"><div className="flex items-center gap-2"><span className="font-display text-xs font-semibold text-slate-200">{incident.type}</span><span className="text-[10px] text-slate-600">{incident.id}</span></div><div className="mt-1 flex items-center gap-1.5 text-[11px] text-slate-500"><MapPin size={12} className="shrink-0 text-[#61d0bc]" /><span className="truncate">{incident.location}</span></div></div><div className="hidden text-right sm:block"><div className="text-[10px] uppercase tracking-[.1em] text-slate-600">Reported</div><div className="mt-1 text-[10px] text-slate-500">{incident.time}</div></div></div>)}{incidents.length === 0 && <div className="px-5 py-10 text-center text-xs text-slate-500">No incidents reported.</div>}</div></section></div>
        <div id="routes" data-reveal className="mt-12"><div className="chapter-rule mb-4"><strong>04</strong> Route context</div><div className="mt-5 grid gap-5 lg:grid-cols-[1.1fr_.9fr]"><MapPanel incidents={incidents} selectedId={selected} onSelect={setSelected} onAcknowledge={acknowledge} onResolve={resolve} /><section className="panel rounded-2xl p-5"><div className="flex items-start justify-between"><div><div className="mb-1 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[.18em] text-[#84a7ff]"><Navigation size={12} />Fleet coverage</div><h2 className="font-display text-lg font-semibold">Active routes</h2></div><button onClick={() => toast("Route history", { description: "Location history syncs from the /locations/latest endpoint." })} className="text-slate-500 transition hover:text-slate-200"><MoreHorizontal size={17} /></button></div><div className="mt-5 space-y-3">{routes.map((route) => <div key={route.name} className="flex items-center gap-3 rounded-xl border border-white/[.07] bg-black/10 p-3 transition hover:bg-white/[.04]"><div className={`grid h-8 w-8 place-items-center rounded-lg ${route.color === "orange" ? "bg-[#f3b84b]/10 text-[#f3b84b]" : route.color === "teal" ? "bg-[#61d0bc]/10 text-[#61d0bc]" : "bg-white/[.06] text-slate-500"}`}><Navigation size={15} fill="currentColor" /></div><div className="min-w-0 flex-1"><div className="flex items-center justify-between gap-2"><span className="font-display text-xs font-semibold text-slate-200">{route.name}</span><span className={`text-[10px] font-semibold ${route.status === "Live" ? "text-[#61d0bc]" : "text-slate-600"}`}>{route.status}</span></div><div className="mt-1 flex items-center justify-between text-[10px] text-slate-500"><span>{route.area}</span><span>{route.distance}</span></div></div></div>)}</div><div className="mt-4 flex items-center justify-between border-t border-white/[.07] pt-4"><div className="flex items-center gap-2 text-[10px] text-slate-500"><span className="h-1.5 w-1.5 rounded-full bg-[#61d0bc]" />GPS updates every 5 sec</div><button onClick={() => toast("Add source", { description: "Connect a new camera or vehicle through POST /streams/start." })} className="flex items-center gap-1 text-[10px] font-semibold text-[#84a7ff] hover:text-[#b1c6ff]"><span className="text-base leading-none">+</span> Add source</button></div></section></div></div>
      </div></main>
    </div>
  </div>;
}

/* motion observer injected below */
