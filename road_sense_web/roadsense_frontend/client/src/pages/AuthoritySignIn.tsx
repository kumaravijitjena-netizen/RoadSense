import { useState } from "react";
import { Link, useLocation } from "wouter";
import { ArrowRight, Building2, Crosshair, ShieldCheck } from "lucide-react";
import { roadsenseApi } from "@/lib/roadsense-api";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { useLanguage } from "@/contexts/LanguageContext";

export default function AuthoritySignIn() {
  const [, navigate] = useLocation();
  const { language } = useLanguage();
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const hi = language === "hi";
  const submit = async (event: React.FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); setSubmitting(true); setError(""); try { await roadsenseApi.authoritySignIn({ authority_id: String(data.get("authority_id") || ""), password: String(data.get("password") || "") }); navigate("/authority", { replace: true }); } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not sign in"); } finally { setSubmitting(false); } };
  return <main className="authority-login"><header><Link href="/" className="auth-brand"><span><Crosshair size={18} /></span><strong>RoadSense.</strong></Link><LanguageSwitcher /></header><section><div className="authority-login__mark"><Building2 size={25} /></div><p>{hi ? "सिर्फ अधिकृत पहुंच" : "Authorized access only"}</p><h1>{hi ? "प्राधिकरण पोर्टल" : "Authority portal"}</h1><span>{hi ? "काम की पुष्टि और रिपोर्ट समाधान के लिए साइन इन करें।" : "Sign in to verify work and resolve reports."}</span><div className="authority-login__temporary"><ShieldCheck size={15} /><span>{hi ? "स्थानीय डेमो पहुंच अभी सक्रिय है" : "Temporary local demo access is active"}</span></div><form onSubmit={submit}><label>{hi ? "प्राधिकरण ID" : "Authority ID"}<input name="authority_id" autoComplete="username" required /></label><label>{hi ? "पासवर्ड" : "Password"}<input name="password" type="password" autoComplete="current-password" required /></label>{error && <small>{error}</small>}<button disabled={submitting}>{submitting ? (hi ? "साइन इन हो रहा है" : "Signing in") : (hi ? "पोर्टल खोलें" : "Open authority portal")}<ArrowRight size={15} /></button></form><div className="authority-login__note"><ShieldCheck size={15} />{hi ? "यह अलग, सुरक्षित प्राधिकरण कार्यक्षेत्र है।" : "This is a separate, secured authority workspace."}</div><Link href="/sign-in">{hi ? "सामान्य उपयोगकर्ता साइन इन" : "Regular user sign in"}</Link></section></main>;
}
