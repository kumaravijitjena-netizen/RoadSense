import { useEffect, useState } from "react";
import { Link, useLocation } from "wouter";
import { ArrowRight, MailCheck, ShieldCheck } from "lucide-react";
import { roadsenseApi } from "@/lib/roadsense-api";

const emailPattern = /^[A-Z0-9](?:[A-Z0-9._%+-]{0,62}[A-Z0-9])?@(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,63}$/i;

export default function SignUp() {
  const [, navigate] = useLocation();
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [verificationSent, setVerificationSent] = useState(false);

  useEffect(() => { void roadsenseApi.currentUser().then(user => { if (user.email) navigate("/", { replace: true }); }).catch(() => setError("JUNIPER is unavailable. Start the backend and try again.")).finally(() => setLoading(false)); }, [navigate]);

  const beginSignUp = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const value = String(data.get("email") || "").trim().toLowerCase();
    const password = String(data.get("password") || "");
    const confirmation = String(data.get("confirmation") || "");
    if (!emailPattern.test(value) || value.includes("..")) return setError("Enter a complete email address, for example name@example.com.");
    if (password !== confirmation) return setError("Passwords do not match.");
    setSubmitting(true); setError("");
    try {
      await roadsenseApi.requestSignUpVerification({ name: String(data.get("name") || ""), email: value, password });
      setEmail(value); setVerificationSent(true);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not send the verification code."); } finally { setSubmitting(false); }
  };

  const completeSignUp = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setSubmitting(true); setError("");
    try { await roadsenseApi.confirmSignUpVerification(email, code); navigate("/"); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Could not verify that code."); }
    finally { setSubmitting(false); }
  };

  return <main className="auth-page"><div className="auth-ambient auth-ambient--signup" /><div className="auth-shell"><div className="auth-brand"><span><ShieldCheck size={18} /></span><strong>JUNIPER.</strong></div><div className="auth-card"><div className="auth-eyebrow">Build a clearer city</div><h1>{verificationSent ? "Confirm your email." : "Start listening."}</h1><p className="auth-copy">{verificationSent ? `Enter the six-digit code sent to ${email}.` : "Create a JUNIPER account. Your email must be confirmed before the account is activated."}</p>{!verificationSent ? <form className="mt-6 space-y-3" onSubmit={beginSignUp}><input className="auth-input" name="name" autoComplete="name" placeholder="Full name" required /><input className="auth-input" name="email" type="email" autoComplete="email" placeholder="name@example.com" required /><input className="auth-input" name="password" type="password" autoComplete="new-password" minLength={8} placeholder="Password (8 characters minimum)" required /><input className="auth-input" name="confirmation" type="password" autoComplete="new-password" placeholder="Confirm password" required />{error && <p className="text-xs text-red-300">{error}</p>}<button className="auth-submit" disabled={loading || submitting}>{submitting ? "Sending code" : "Send verification code"} <ArrowRight size={15} /></button></form> : <form className="mt-6 space-y-3" onSubmit={completeSignUp}><input className="auth-input" inputMode="numeric" maxLength={6} value={code} onChange={event => setCode(event.target.value.replace(/\D/g, ""))} placeholder="Six-digit code" required />{error && <p className="text-xs text-red-300">{error}</p>}<button className="auth-submit" disabled={submitting || code.length !== 6}>{submitting ? "Confirming" : "Verify email and create account"} <MailCheck size={15} /></button><button type="button" className="auth-recovery-link" onClick={() => { setVerificationSent(false); setCode(""); setError(""); }}>Use a different email</button></form>}<div className="auth-footer">Already have access? <Link href="/sign-in">Sign in</Link></div></div></div></main>;
}
