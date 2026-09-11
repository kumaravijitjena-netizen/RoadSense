import { Link } from "wouter";
import { ArrowRight, Crosshair } from "lucide-react";
import { roadsenseApi } from "@/lib/roadsense-api";

export default function SignUp() {
  return <main className="auth-page"><div className="auth-ambient auth-ambient--signup" /><div className="auth-shell"><div className="auth-brand"><span><Crosshair size={18} /></span><strong>RoadSense.</strong></div><div className="auth-card"><div className="auth-eyebrow">Build a clearer city</div><h1>Start listening.</h1><p className="auth-copy">Create your workspace and authorize Gmail in one secure step.</p><button className="auth-submit" type="button" onClick={() => window.location.assign(roadsenseApi.googleSignInUrl())}>Continue with Google <ArrowRight size={15} /></button><div className="auth-footer">Already have access? <Link href="/sign-in">Sign in</Link></div></div></div></main>;
}
