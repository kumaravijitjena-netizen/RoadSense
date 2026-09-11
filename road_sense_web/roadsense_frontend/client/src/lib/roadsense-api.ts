const API_BASE = import.meta.env.VITE_ROADSENSE_API_URL ?? (window.location.port === "3000" ? "http://127.0.0.1:8001" : window.location.origin);

export type BackendIncident = {
  id: string;
  created_at: string;
  updated_at: string;
  source_id: string;
  model_name: string;
  hazard_type: string;
  confidence: number;
  latitude: number | null;
  longitude: number | null;
  status: "open" | "acknowledged" | "resolved" | "false_positive";
  details: string | null;
  image_path: string | null;
  reporter_name: string | null;
  reporter_email: string | null;
  location_name: string | null;
};

export type StreamStatus = { running: boolean; source_id: string | null; fps: number; error: string | null; model?: string };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { credentials: "include", headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) }, ...init });
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? `Request failed (${response.status})`);
  return response.json() as Promise<T>;
}

export const roadsenseApi = {
  baseUrl: API_BASE,
  health: () => request<{ status: string; stream: StreamStatus }>("/health"),
  incidents: () => request<BackendIncident[]>("/incidents"),
  locations: () => request<Array<{ source_id: string; latitude: number; longitude: number; captured_at: string }>>("/locations/latest"),
  postLocation: (location: { source_id: string; latitude: number; longitude: number; accuracy_m?: number }) => request("/locations", { method: "POST", body: JSON.stringify(location) }),
  streamStatus: () => request<StreamStatus>("/streams/status"),
  startStream: () => request<StreamStatus>("/streams/start", { method: "POST", body: JSON.stringify({ source: "0", source_id: "camera-1", model: "v2", confidence: 0.35, auto_notify: true }) }),
  stopStream: () => request<{ status: string }>("/streams/stop", { method: "POST" }),
  updateIncident: (id: string, update: { status?: BackendIncident["status"]; details?: string }) => request<BackendIncident>(`/incidents/${id}`, { method: "PATCH", body: JSON.stringify(update) }),
  notify: (id: string) => request<{ status: string }>(`/incidents/${id}/notify`, { method: "POST" }),
  reportIncident: (report: { hazard_type: "pothole" | "manhole" | "other"; latitude: number; longitude: number; details?: string }) => request<BackendIncident>("/incidents", { method: "POST", body: JSON.stringify(report) }),
  reportIncidentWithPhoto: async (report: { hazard_type: "pothole" | "manhole" | "other"; reporter_name: string; reporter_email?: string; location_name: string; latitude?: number; longitude?: number; details?: string; photo?: File | null }) => {
    const body = new FormData();
    body.set("hazard_type", report.hazard_type); body.set("reporter_name", report.reporter_name); body.set("location_name", report.location_name);
    if (report.reporter_email) body.set("reporter_email", report.reporter_email);
    if (report.latitude !== undefined) body.set("latitude", String(report.latitude));
    if (report.longitude !== undefined) body.set("longitude", String(report.longitude));
    if (report.details) body.set("details", report.details);
    if (report.photo) body.set("photo", report.photo);
    const response = await fetch(`${API_BASE}/incidents/report`, { method: "POST", body, credentials: "include" });
    if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? `Request failed (${response.status})`);
    return response.json() as Promise<BackendIncident>;
  },
  analyzeBrowserFrame: async (frame: Blob, location?: { latitude: number; longitude: number }) => {
    const body = new FormData();
    body.set("file", frame, "camera-frame.jpg");
    const query = new URLSearchParams({ model: "v2", confidence: "0.35", source_id: "browser-camera" });
    if (location) { query.set("latitude", String(location.latitude)); query.set("longitude", String(location.longitude)); }
    const response = await fetch(`${API_BASE}/streams/browser-frame?${query}`, { method: "POST", body, credentials: "include" });
    if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? `Request failed (${response.status})`);
    return response.json() as Promise<{ count: number; detections: Array<{ class: string; confidence: number; box: number[] }>; incidents: BackendIncident[]; frame_width: number; frame_height: number }>;
  },
  googleSignInUrl: () => `${API_BASE}/auth/google/start?return_to=${encodeURIComponent(`${window.location.origin}/`)}`,
  currentUser: () => request<{ email: string | null; gmail_connected: boolean }>("/auth/me"),
  streamUrl: () => `${API_BASE}/streams/mjpeg`,
  socketUrl: () => API_BASE.replace(/^http/, "ws") + "/ws/live",
};
