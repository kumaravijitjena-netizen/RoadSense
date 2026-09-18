import { useEffect, useState } from "react";
import { Link, useLocation } from "wouter";
import { ArrowLeft, Crosshair } from "lucide-react";
import { roadsenseApi } from "@/lib/roadsense-api";
import { AccountFlipCard } from "@/components/AccountFlipCard";

type Account = { email: string | null; name: string | null; gmail_connected: boolean; incident_count: number };

export default function AccountPage() {
  const [, navigate] = useLocation();
  const [account, setAccount] = useState<Account | null>(null);
  useEffect(() => { void roadsenseApi.currentUser().then(user => { if (!user.email) navigate("/sign-in", { replace: true }); else setAccount(user); }); }, [navigate]);
  const signOut = async () => {
    if (!window.confirm("Log out of JUNIPER on this device?")) return;
    await roadsenseApi.signOut();
    navigate("/sign-in", { replace: true });
  };
  if (!account) return <main className="auth-page"><div className="auth-ambient" /></main>;
  const initials = (account.name || account.email || "AK").split(/[\s@]+/).filter(Boolean).slice(0, 2).map(value => value[0]).join("").toUpperCase();
  const avatarUrl = `https://api.dicebear.com/9.x/initials/svg?seed=${encodeURIComponent(account.name || account.email || "JUNIPER")}&backgroundColor=61d0bc&textColor=0b1019&fontSize=42`;
  return <main className="account-stage"><header className="account-header"><Link href="/" className="auth-brand"><span><Crosshair size={18} /></span><strong>JUNIPER.</strong></Link><button type="button" className="account-back" onClick={() => navigate("/")}><ArrowLeft size={15} />Dashboard</button></header><div className="account-stage__backdrop" aria-hidden="true"><span /><span /><span /></div><div className="account-stage__card"><AccountFlipCard initials={initials} name={account.name || "JUNIPER user"} email={account.email || ""} avatarUrl={avatarUrl} incidentCount={account.incident_count} gmailConnected={account.gmail_connected} onInfo={() => navigate("/account/info")} onSignOut={() => void signOut()} /></div></main>;
}
