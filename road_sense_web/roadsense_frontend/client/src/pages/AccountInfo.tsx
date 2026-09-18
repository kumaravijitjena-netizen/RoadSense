import { useEffect, useState } from "react";
import { Link, useLocation } from "wouter";
import { ArrowLeft, CheckCircle2, Crosshair, KeyRound, Mail, Save, UserRound } from "lucide-react";
import { roadsenseApi } from "@/lib/roadsense-api";

type Account = {
  email: string | null;
  name: string | null;
  gmail_connected: boolean;
  notify_email: boolean;
  password_account: boolean;
};

export default function AccountInfoPage() {
  const [, navigate] = useLocation();
  const [account, setAccount] = useState<Account | null>(null);
  const [name, setName] = useState("");
  const [notify, setNotify] = useState(true);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    void roadsenseApi.currentUser().then(user => {
      if (!user.email) {
        navigate("/sign-in", { replace: true });
        return;
      }
      setAccount(user);
      setName(user.name || "");
      setNotify(user.notify_email);
    });
  }, [navigate]);

  const saveProfile = async () => {
    if (!name.trim()) return setMessage("Enter a display name.");
    setSaving(true);
    try {
      const user = await roadsenseApi.updateProfile({ name: name.trim(), notify_email: notify });
      setAccount(user);
      setMessage("Profile saved.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not save profile.");
    } finally {
      setSaving(false);
    }
  };

  const updatePassword = async () => {
    if (newPassword.length < 8) return setMessage("Use at least 8 characters for the new password.");
    setSaving(true);
    try {
      await roadsenseApi.changePassword({ current_password: currentPassword, new_password: newPassword });
      setCurrentPassword("");
      setNewPassword("");
      setMessage("Password updated.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not update password.");
    } finally {
      setSaving(false);
    }
  };

  if (!account) return <main className="auth-page"><div className="auth-ambient" /></main>;

  return <main className="account-page">
    <header className="account-header">
      <Link href="/" className="auth-brand"><span><Crosshair size={18} /></span><strong>RoadSense.</strong></Link>
      <button type="button" className="account-back" onClick={() => navigate("/account")}><ArrowLeft size={15} />Account</button>
    </header>
    <section className="account-main account-main--single">
      <p className="section-kicker">Account settings</p>
      <h2>Profile and delivery</h2>
      {message && <p className="account-message">{message}</p>}
      <section className="account-section">
        <div className="account-section__heading"><UserRound size={18} /><div><strong>Profile</strong><span>Your report identity</span></div></div>
        <label className="account-label">Display name<input className="auth-input" value={name} onChange={event => setName(event.target.value)} /></label>
        <label className="account-toggle"><input type="checkbox" checked={notify} onChange={event => setNotify(event.target.checked)} /><span><strong>Email updates</strong><small>Receive an update when RoadSense processes your report.</small></span></label>
        <button type="button" className="account-action" disabled={saving} onClick={() => void saveProfile()}><Save size={15} />Save profile</button>
      </section>
      <section className="account-section">
        <div className="account-section__heading"><Mail size={18} /><div><strong>Gmail delivery</strong><span>{account.gmail_connected ? "Reports can send from your connected Gmail account." : "Connect Gmail to send reports from your own account."}</span></div>{account.gmail_connected ? <CheckCircle2 size={18} /> : <button type="button" className="account-link" onClick={() => { window.location.href = roadsenseApi.googleSignInUrl(); }}>Connect</button>}</div>
      </section>
      {account.password_account && <section className="account-section">
        <div className="account-section__heading"><KeyRound size={18} /><div><strong>Password and security</strong><span>Change your local RoadSense password.</span></div></div>
        <div className="account-passwords"><input className="auth-input" type="password" placeholder="Current password" value={currentPassword} onChange={event => setCurrentPassword(event.target.value)} /><input className="auth-input" type="password" placeholder="New password (8 characters minimum)" value={newPassword} onChange={event => setNewPassword(event.target.value)} /></div>
        <button type="button" className="account-action" disabled={saving} onClick={() => void updatePassword()}>Update password</button>
      </section>}
    </section>
  </main>;
}
