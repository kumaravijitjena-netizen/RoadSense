import { useEffect, useState } from "react";
import { Link, useLocation } from "wouter";
import { ArrowRight, CheckCircle2, Crosshair } from "lucide-react";
import { roadsenseApi } from "@/lib/roadsense-api";

export default function SignIn() {
  const [, navigate] = useLocation();
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { void roadsenseApi.currentUser().then(user => { if (user.email) navigate("/", { replace: true }); }).catch(() => setError("RoadSense is unavailable. Start the backend and try again.")).finally(() => setLoading(false)); }, [navigate]);
  const signIn = async (event: React.FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); setSubmitting(true); setError(""); try { await roadsenseApi.signIn({ email: String(data.get("email") || ""), password: String(data.get("password") || "") }); navigate("/"); } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not sign in"); } finally { setSubmitting(false); } };
  return <main className="auth-page"><div className="auth-ambient" /><div className="auth-shell"><div className="auth-brand"><span><Crosshair size={18} /></span><strong>RoadSense.</strong></div><div className="auth-card"><div className="auth-eyebrow">Operations control</div><h1>Welcome back.</h1><p className="auth-copy">Sign in to manage and report road hazards.</p><form className="mt-6 space-y-3" onSubmit={signIn}><input className="auth-input" name="email" type="email" autoComplete="email" placeholder="Email address" required /><input className="auth-input" name="password" type="password" autoComplete="current-password" placeholder="Password" required />{error && <p className="text-xs text-red-300">{error}</p>}<button className="auth-submit" disabled={loading || submitting}>{submitting ? "Signing in" : "Sign in"} <ArrowRight size={15} /></button></form><Link href="/reset-password" className="auth-recovery-link">Forgot password?</Link><div className="my-5 flex items-center gap-3 text-[10px] uppercase tracking-[.12em] text-slate-600"><span className="h-px flex-1 bg-white/10" />or<span className="h-px flex-1 bg-white/10" /></div><button className="auth-submit border border-white/15 !bg-transparent !text-slate-100" type="button" disabled={loading || submitting} onClick={() => window.location.assign(roadsenseApi.googleSignInUrl())}>Continue with Google <CheckCircle2 size={15} /></button><Link href="/authority/sign-in" className="authority-login-link">Authority sign in <ArrowRight size={14} /></Link><div className="auth-footer">New to RoadSense? <Link href="/sign-up">Create an account</Link></div></div></div></main>;
}
