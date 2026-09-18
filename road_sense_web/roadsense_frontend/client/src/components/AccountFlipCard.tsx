import { useState } from "react";
import { ArrowRight, Info, LogOut, Mail, Repeat2 } from "lucide-react";

type AccountFlipCardProps = {
  initials: string;
  name: string;
  email: string;
  avatarUrl: string;
  incidentCount: number;
  gmailConnected: boolean;
  onInfo: () => void;
  onSignOut: () => void;
};

export function AccountFlipCard({ initials, name, email, avatarUrl, incidentCount, gmailConnected, onInfo, onSignOut }: AccountFlipCardProps) {
  const [flipped, setFlipped] = useState(false);
  return <div className="account-flip">
    <div className={`account-flip__inner ${flipped ? "is-flipped" : ""}`}>
      <button type="button" className="account-flip__front" onClick={() => setFlipped(true)} aria-label="Show account options"><span className="account-profile-photo"><img src={avatarUrl} alt="" onError={event => { event.currentTarget.style.display = "none"; }} /><span>{initials}</span></span><span className="account-flip__copy"><strong>{name}</strong><small>{email}</small></span><span className="account-flip__hint">Tap for options <Repeat2 size={14} aria-hidden="true" /></span></button>
      <div className="account-flip__back"><span className="account-flip__backhead"><Info size={17} /><strong>Account</strong><button type="button" className="account-flip__turn" onClick={() => setFlipped(false)} aria-label="Return to profile"><Repeat2 size={14} /></button></span><span className="account-flip__metric"><b>{incidentCount}</b><small>reports submitted</small></span><span className="account-flip__delivery"><Mail size={15} />{gmailConnected ? "Gmail delivery connected" : "JUNIPER delivery active"}</span><button type="button" className="account-flip__connect" onClick={onInfo}>Account info <ArrowRight size={14} /></button><button type="button" className="account-flip__logout" onClick={onSignOut}><LogOut size={14} />Log out</button></div>
    </div>
  </div>;
}
