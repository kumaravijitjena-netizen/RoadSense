import { Link } from "wouter";
import { ArrowLeft, Crosshair, Radar } from "lucide-react";

export default function NotFound() {
  return <main className="error-page"><div className="error-orbit"><Radar size={38} /></div><div className="auth-brand"><span><Crosshair size={18} /></span><strong>RoadSense.</strong></div><div className="error-code">404</div><h1>Signal lost.</h1><p>This route drifted outside the mapped network. Let’s get you back to the control room.</p><Link href="/" className="error-link"><ArrowLeft size={15} /> Return to overview</Link></main>;
}
