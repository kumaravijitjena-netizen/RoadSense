const API_BASE = import.meta.env.VITE_ROADSENSE_API_URL ?? (window.location.port === "3000" ? `${window.location.protocol}//${window.location.hostname}:8001` : window.location.origin);

export type BackendIncident = {
  id: string;
  created_at: string;
  updated_at: string;
  source_id: string;
  model_name: string;
  hazard_type: string;
  confidence: number;
  detection_count: number;
  latitude: number | null;
  longitude: number | null;
  status: "open" | "acknowledged" | "resolved" | "false_positive";
  details: string | null;
  image_path: string | null;
  reporter_name: string | null;
  reporter_email: string | null;
  location_name: string | null;
  address_line: string | null;
  area: string | null;
  city: string | null;
  postal_code: string | null;
  landmark: string | null;
  location_source: string | null;
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
  zones: () => request<Array<{ zone_key: string; latitude: number; longitude: number; count: number; color: "green" | "blue" | "yellow" | "orange" | "red" }>>("/zones"),
  incident: (id: string) => request<BackendIncident & { resolution_proofs: Array<{ id: string; authority_email: string; note: string; media_path: string | null; created_at: string }>; authority_updates: Array<{ id: string; authority_email: string; message: string; status: string; created_at: string }> }>(`/incidents/${id}`),
  authorityIncidents: () => request<BackendIncident[]>("/authority/incidents"),
  postAuthorityUpdate: (incidentId: string, update: { message: string; status: "acknowledged" | "resolved" }) => request<BackendIncident>(`/authority/incidents/${incidentId}/update`, { method: "POST", body: JSON.stringify(update) }),
  submitResolutionProof: async (incidentId: string, proof: { note: string; file?: File | null }) => {
    const body = new FormData(); body.set("note", proof.note); if (proof.file) body.set("proof", proof.file);
    const response = await fetch(`${API_BASE}/authority/incidents/${incidentId}/proof`, { method: "POST", body, credentials: "include" });
    if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? `Request failed (${response.status})`);
    return response.json() as Promise<{ incident: BackendIncident }>;
  },
  clearIncidentHistory: () => request<{ status: string; count: number }>("/incidents", { method: "DELETE" }),
  locations: () => request<Array<{ source_id: string; latitude: number; longitude: number; captured_at: string }>>("/locations/latest"),
  postLocation: (location: { source_id: string; latitude: number; longitude: number; accuracy_m?: number }) => request("/locations", { method: "POST", body: JSON.stringify(location) }),
  streamStatus: () => request<StreamStatus>("/streams/status"),
  smsReporting: () => request<{ enabled: boolean; number: string | null }>("/sms/reporting"),
  startStream: () => request<StreamStatus>("/streams/start", { method: "POST", body: JSON.stringify({ source: "0", source_id: "camera-1", model: "roadsense_v8", confidence: 0.20, auto_notify: true }) }),
  stopStream: () => request<{ status: string }>("/streams/stop", { method: "POST" }),
  updateIncident: (id: string, update: { status?: BackendIncident["status"]; details?: string }) => request<BackendIncident>(`/incidents/${id}`, { method: "PATCH", body: JSON.stringify(update) }),
  notify: (id: string) => request<{ status: string }>(`/incidents/${id}/notify`, { method: "POST" }),
  reportIncident: (report: { hazard_type: string; latitude: number; longitude: number; details?: string }) => request<BackendIncident>("/incidents", { method: "POST", body: JSON.stringify(report) }),
  mediaUrl: (path: string) => `${API_BASE}/media/${encodeURIComponent(path)}`,
  photoLocation: async (photo: File) => {
    const body = new FormData(); body.set("photo", photo);
    const response = await fetch(`${API_BASE}/media/photo-location`, { method: "POST", body });
    if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "Could not inspect photo location");
    return response.json() as Promise<{ found: boolean; latitude?: number; longitude?: number; source?: "photo_metadata"; reason?: string }>;
  },
  reportIncidentWithPhoto: async (report: { hazard_type: string; reporter_name: string; reporter_email?: string; location_name: string; address_line?: string; area?: string; city?: string; postal_code?: string; landmark?: string; latitude?: number; longitude?: number; location_source?: "manual_pin"; details?: string; photo?: File | null }) => {
    const body = new FormData();
    body.set("hazard_type", report.hazard_type); body.set("reporter_name", report.reporter_name); body.set("location_name", report.location_name);
    if (report.reporter_email) body.set("reporter_email", report.reporter_email);
    if (report.address_line) body.set("address_line", report.address_line);
    if (report.area) body.set("area", report.area);
    if (report.city) body.set("city", report.city);
    if (report.postal_code) body.set("postal_code", report.postal_code);
    if (report.landmark) body.set("landmark", report.landmark);
    if (report.latitude !== undefined) body.set("latitude", String(report.latitude));
    if (report.longitude !== undefined) body.set("longitude", String(report.longitude));
    if (report.location_source) body.set("location_source", report.location_source);
    if (report.details) body.set("details", report.details);
    if (report.photo) body.set("photo", report.photo);
    const response = await fetch(`${API_BASE}/incidents/report`, { method: "POST", body, credentials: "include" });
    if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? `Request failed (${response.status})`);
    return response.json() as Promise<BackendIncident>;
  },
  analyzeBrowserFrame: async (frame: Blob, location?: { latitude: number; longitude: number }) => {
    const body = new FormData();
    body.set("file", frame, "camera-frame.jpg");
    const query = new URLSearchParams({ model: "roadsense_v8", confidence: "0.20", source_id: "browser-camera" });
    if (location) { query.set("latitude", String(location.latitude)); query.set("longitude", String(location.longitude)); }
    const response = await fetch(`${API_BASE}/streams/browser-frame?${query}`, { method: "POST", body, credentials: "include" });
    if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? `Request failed (${response.status})`);
    return response.json() as Promise<{ count: number; detections: Array<{ class: string; confidence: number; box: number[] }>; incidents: BackendIncident[]; frame_width: number; frame_height: number }>;
  },
  googleSignInUrl: () => `${API_BASE}/auth/google/start?return_to=${encodeURIComponent(`${window.location.origin}/`)}`,
  currentUser: () => request<{ email: string | null; name: string | null; gmail_connected: boolean; notify_email: boolean; incident_count: number; password_account: boolean }>("/auth/me"),
  signOut: () => request<void>("/auth/sign-out", { method: "POST" }),
  updateProfile: (profile: { name: string; notify_email: boolean }) => request<{ email: string; name: string; gmail_connected: boolean; notify_email: boolean; incident_count: number; password_account: boolean }>("/auth/profile", { method: "PATCH", body: JSON.stringify(profile) }),
  changePassword: (passwords: { current_password: string; new_password: string }) => request<{ status: string }>("/auth/change-password", { method: "POST", body: JSON.stringify(passwords) }),
  requestSignUpVerification: (account: { name: string; email: string; password: string }) => request<{ status: string }>("/auth/sign-up/request", { method: "POST", body: JSON.stringify(account) }),
  confirmSignUpVerification: (email: string, code: string) => request<{ email: string; name: string; gmail_connected: boolean }>("/auth/sign-up/confirm", { method: "POST", body: JSON.stringify({ email, code }) }),
  signIn: (account: { email: string; password: string }) => request<{ email: string; name: string; gmail_connected: boolean }>("/auth/sign-in", { method: "POST", body: JSON.stringify(account) }),
  authoritySignIn: (account: { authority_id: string; password: string }) => request<{ email: string; name: string; gmail_connected: boolean }>("/auth/authority/sign-in", { method: "POST", body: JSON.stringify(account) }),
  requestPasswordReset: (email: string) => request<{ status: string }>("/auth/password-reset/request", { method: "POST", body: JSON.stringify({ email }) }),
  verifyPasswordResetCode: (email: string, code: string) => request<{ status: string }>("/auth/password-reset/verify", { method: "POST", body: JSON.stringify({ email, code }) }),
  confirmPasswordReset: (email: string, code: string, password: string) => request<{ status: string }>("/auth/password-reset/confirm", { method: "POST", body: JSON.stringify({ email, code, password }) }),
  streamUrl: () => `${API_BASE}/streams/mjpeg`,
  socketUrl: () => API_BASE.replace(/^http/, "ws") + "/ws/live",
};
