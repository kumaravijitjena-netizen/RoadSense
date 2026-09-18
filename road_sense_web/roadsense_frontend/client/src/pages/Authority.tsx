import { useEffect, useState } from "react";
import { Link, useLocation } from "wouter";
import { ArrowLeft, CheckCircle2, Crosshair, FileCheck2, MapPin, PlayCircle, Upload } from "lucide-react";
import { roadsenseApi, type BackendIncident } from "@/lib/roadsense-api";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { useLanguage } from "@/contexts/LanguageContext";

export default function AuthorityPage() {
  const [, navigate] = useLocation();
  const { language } = useLanguage();
  const [incidents, setIncidents] = useState<BackendIncident[]>([]);
  const [zones, setZones] = useState<Array<{ zone_key: string; count: number; color: string }>>([]);
  const [selected, setSelected] = useState<BackendIncident | null>(null);
  const [note, setNote] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const hi = language === "hi";
  const refresh = async () => { const [records, nextZones] = await Promise.all([roadsenseApi.authorityIncidents(), roadsenseApi.zones()]); setIncidents(records); setZones(nextZones); setSelected(current => records.find(item => item.id === current?.id) ?? records[0] ?? null); };
  useEffect(() => { void roadsenseApi.currentUser().then(user => { if (!user.email) navigate("/authority/sign-in", { replace: true }); else return refresh().catch(error => { if (error instanceof Error && /not an enabled|Sign in as an authority/.test(error.message)) navigate("/authority/sign-in", { replace: true }); else setMessage(error instanceof Error ? error.message : "Unable to load authority workspace."); }); }); }, [navigate]);
  const submit = async () => {
    if (!selected || note.trim().length < 4) { setMessage(hi ? "कृपया काम का विवरण लिखें।" : "Describe the completed work before submitting."); return; }
    setSaving(true); setMessage("");
    try { await roadsenseApi.submitResolutionProof(selected.id, { note: note.trim(), file }); setNote(""); setFile(null); setMessage(hi ? "प्रमाण जमा हो गया और घटना का समाधान कर दिया गया।" : "Proof submitted and incident marked resolved."); await refresh(); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Could not submit proof."); }
    finally { setSaving(false); }
  };
  const startWork = async () => {
    if (!selected || note.trim().length < 3) { setMessage(hi ? "काम शुरू होने की जानकारी लिखें।" : "Add a short work update before posting."); return; }
    setSaving(true); setMessage("");
    try { await roadsenseApi.postAuthorityUpdate(selected.id, { message: note.trim(), status: "acknowledged" }); setNote(""); setMessage(hi ? "काम शुरू होने की सूचना साझा कर दी गई।" : "Work-started update is now visible publicly."); await refresh(); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Could not post update."); }
    finally { setSaving(false); }
  };
  return <main className="authority-page"><header className="authority-header"><Link href="/" className="auth-brand"><span><Crosshair size={18} /></span><strong>RoadSense.</strong></Link><div className="flex items-center gap-3"><LanguageSwitcher /><Link href="/" className="account-back"><ArrowLeft size={15} />{hi ? "डैशबोर्ड" : "Dashboard"}</Link></div></header><section className="authority-intro"><p>{hi ? "प्राधिकरण कार्यक्षेत्र" : "Authority workspace"}</p><h1>{hi ? "रिपोर्ट की गई सड़कों पर कार्रवाई करें।" : "Close the loop on reported roads."}</h1><span>{hi ? "काम शुरू होने की जानकारी दें, प्रमाण जोड़ें और समाधान दर्ज करें।" : "Share when work begins, add proof, and record a resolution."}</span></section><section className="authority-zones"><strong>{hi ? "लाइव प्राथमिकता क्षेत्र" : "Live priority zones"}</strong><span>{zones.map(zone => <i key={zone.zone_key} className={`zone-pill ${zone.color}`}>{zone.color} · {zone.count}</i>)}</span><small>{hi ? "पीला 3, नारंगी 5 और लाल 8+ रिपोर्ट पर ईमेल एस्केलेशन भेजता है।" : "Yellow at 3, orange at 5, and red at 8+ reports send escalation emails."}</small></section><div className="authority-layout"><section className="authority-list"><div className="authority-list__head"><h2>{hi ? "रिपोर्ट" : "Reports"}</h2><span>{incidents.filter(item => item.status !== "resolved").length} {hi ? "खुली" : "open"}</span></div>{incidents.map(incident => <button key={incident.id} type="button" onClick={() => setSelected(incident)} className={`authority-incident ${selected?.id === incident.id ? "is-selected" : ""}`}><span className={`authority-dot ${incident.status}`} /><span><strong>{incident.hazard_type}</strong><small><MapPin size={12} />{[incident.location_name, incident.address_line, incident.city].filter(Boolean).join(", ") || (hi ? "स्थान उपलब्ध नहीं" : "Location not supplied")}</small></span><em>{incident.status}</em></button>)}</section><section className="authority-detail">{selected ? <><div className="authority-detail__title"><div><p>{hi ? "चुनी गई घटना" : "Selected incident"}</p><h2>{selected.hazard_type}</h2></div><span className={`authority-status ${selected.status}`}>{selected.status}</span></div><div className="authority-address"><MapPin size={18} /><div><strong>{selected.location_name || (hi ? "स्थान उपलब्ध नहीं" : "Location not supplied")}</strong><span>{[selected.address_line, selected.area, selected.city, selected.postal_code, selected.landmark].filter(Boolean).join(", ")}</span>{selected.latitude !== null && selected.longitude !== null && <a href={`https://www.google.com/maps?q=${selected.latitude},${selected.longitude}`} target="_blank" rel="noreferrer">{hi ? "मानचित्र पर खोलें" : "Open on map"}</a>}</div></div>{selected.image_path && <img className="authority-evidence" src={roadsenseApi.mediaUrl(selected.image_path)} alt="Reported incident evidence" />}<div className="authority-proof"><div className="flex items-center gap-2"><FileCheck2 size={18} /><h3>{hi ? "कार्य अपडेट और प्रमाण" : "Work update and proof"}</h3></div><textarea value={note} onChange={event => setNote(event.target.value)} placeholder={hi ? "काम शुरू होने या मरम्मत का विवरण" : "Share work-started or repair details"} rows={4} /><div className="authority-actions"><button type="button" className="authority-work" disabled={saving || selected.status !== "open"} onClick={() => void startWork()}><PlayCircle size={16} />{hi ? "काम शुरू करें" : "Mark work started"}</button><button type="button" disabled={saving || selected.status === "resolved"} onClick={() => void submit()}><CheckCircle2 size={16} />{saving ? (hi ? "जमा हो रहा है" : "Submitting") : (hi ? "प्रमाण जमा करें और समाधान करें" : "Submit proof and resolve")}</button></div><label><Upload size={15} /><span>{file ? file.name : (hi ? "फोटो या वीडियो जोड़ें" : "Attach completion photo or video")}</span><input type="file" accept="image/jpeg,image/png,image/webp,video/mp4,video/webm,video/quicktime" onChange={event => setFile(event.target.files?.[0] ?? null)} /></label>{message && <p className="authority-message">{message}</p>}</div></> : <div className="authority-empty">{hi ? "कोई रिपोर्ट नहीं मिली।" : "No reports found."}</div>}</section></div></main>;
}
