import { useState } from "react";
import { Link, useLocation } from "wouter";
import { ArrowRight, Crosshair, KeyRound } from "lucide-react";
import { roadsenseApi } from "@/lib/roadsense-api";

export default function ResetPassword() {
  const [, navigate] = useLocation();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [codeRequested, setCodeRequested] = useState(false);
  const [codeVerified, setCodeVerified] = useState(false);
  const requestReset = async (event: React.FormEvent) => { event.preventDefault(); setSubmitting(true); setMessage(""); try { await roadsenseApi.requestPasswordReset(email); setCodeRequested(true); setMessage("If that email has a RoadSense password account, a six-digit code is on its way."); } catch { setMessage("We could not request a code. Please try again."); } finally { setSubmitting(false); } };
  const verifyCode = async (event: React.FormEvent) => { event.preventDefault(); setSubmitting(true); setMessage(""); try { await roadsenseApi.verifyPasswordResetCode(email, code); setCodeVerified(true); } catch (error) { setMessage(error instanceof Error ? error.message : "Could not verify code."); } finally { setSubmitting(false); } };
  const confirmReset = async (event: React.FormEvent) => { event.preventDefault(); if (password !== confirmation) return setMessage("Passwords do not match."); setSubmitting(true); setMessage(""); try { await roadsenseApi.confirmPasswordReset(email, code, password); navigate("/sign-in", { replace: true }); } catch (error) { setMessage(error instanceof Error ? error.message : "Could not reset password."); } finally { setSubmitting(false); } };
  const title = !codeRequested ? "Reset your password." : !codeVerified ? "Confirm your code." : "Set a new password.";
  const description = !codeRequested ? "Enter the email for your password account and we’ll send a six-digit recovery code." : !codeVerified ? "Enter the six-digit code from your email to continue." : "Choose a new password for your RoadSense account.";
  return <main className="auth-page"><div className="auth-ambient" /><div className="auth-shell"><Link href="/" className="auth-brand"><span><Crosshair size={18} /></span><strong>RoadSense.</strong></Link><div className="auth-card"><div className="auth-eyebrow">Account recovery</div><h1>{title}</h1><p className="auth-copy">{description}</p><form className="mt-6 space-y-3" onSubmit={!codeRequested ? requestReset : !codeVerified ? verifyCode : confirmReset}><input className="auth-input" type="email" value={email} onChange={event => setEmail(event.target.value)} autoComplete="email" placeholder="Email address" required readOnly={codeRequested} />{codeRequested && !codeVerified && <input className="auth-input" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} value={code} onChange={event => setCode(event.target.value.replace(/\D/g, ""))} placeholder="Six-digit code" required />}{codeVerified && <><input className="auth-input" type="password" value={password} onChange={event => setPassword(event.target.value)} minLength={8} autoComplete="new-password" placeholder="New password (8 characters minimum)" required /><input className="auth-input" type="password" value={confirmation} onChange={event => setConfirmation(event.target.value)} autoComplete="new-password" placeholder="Confirm new password" required /></>}{message && <p className="text-xs text-slate-300">{message}</p>}<button className="auth-submit" disabled={submitting}>{submitting ? "Please wait" : !codeRequested ? "Send recovery code" : !codeVerified ? "Confirm code" : "Save new password"}<ArrowRight size={15} /></button></form><div className="mt-5 flex items-center gap-2 text-xs text-slate-400"><KeyRound size={15} className="text-[#61d0bc]" />Codes expire after 30 minutes and can only be used once.</div><div className="auth-footer"><Link href="/sign-in">Return to sign in</Link></div></div></div></main>;
}
