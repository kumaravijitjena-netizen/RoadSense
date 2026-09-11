import { Link } from "wouter";
import { ArrowRight, Crosshair } from "lucide-react";
import { roadsenseApi } from "@/lib/roadsense-api";

export default function SignIn() {
  return <main className="auth-page"><div className="auth-ambient" /><div className="auth-shell"><div className="auth-brand"><span><Crosshair size={18} /></span><strong>RoadSense.</strong></div><div className="auth-card"><div className="auth-eyebrow">Operations control</div><h1>Welcome back.</h1><p className="auth-copy">Connect your Google account to send reports from your own Gmail.</p><button className="auth-submit" type="button" onClick={() => window.location.assign(roadsenseApi.googleSignInUrl())}>Continue with Google <ArrowRight size={15} /></button><div className="auth-footer">New to RoadSense? <Link href="/sign-up">Create an account</Link></div></div></div></main>;
}
