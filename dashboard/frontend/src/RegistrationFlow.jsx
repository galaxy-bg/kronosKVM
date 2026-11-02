import React, {useEffect, useRef, useState} from 'react';
import {Check, CheckCircle2, LoaderCircle, X} from 'lucide-react';
import './registration-flow.css';

export function licenseIssue(license, device, customers, tick = Date.now()) {
  const customer = customers.find(c => c.id === license.customer_id);
  if (!customer || customer.archived_at) return 'Customer unavailable';
  if (license.status !== 'ACTIVE') return 'License is not active';
  if (license.expires_at && new Date(license.expires_at).getTime() <= tick) return 'License expired';
  if (device.license?.id && device.license.id !== license.id) return 'Release the existing license binding first';
  if (!(license.device_ids || []).includes(device.id) && license.used_devices >= license.max_devices) return 'No free device slots';
  return '';
}

export default function RegistrationFlow({device, candidates, licenses, customers, api, onClose, onApproved, onManageLicenses, onVpn}) {
  const eligible = licenses.filter(l => !licenseIssue(l, device, customers));
  const preferred = eligible.filter(l => l.customer_id === device.customer_id);
  const proof = device.approval_identity;
  const proven = proof && candidates.findIndex(c => c.installation_id === proof.installation_id && c.public_key === proof.public_key);
  const [identity, setIdentity] = useState(proven >= 0 && proof ? String(proven) : candidates.length === 1 ? '0' : '');
  const [licenseId, setLicenseId] = useState(device.license?.id || (preferred.length === 1 ? preferred[0].id : eligible.length === 1 ? eligible[0].id : ''));
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [approved, setApproved] = useState(false);
  const [live, setLive] = useState(device);
  const currentApi = useRef(api); currentApi.current = api;
  const selected = licenses.find(l => l.id === licenseId);
  const issue = selected ? licenseIssue(selected, device, customers) : 'Select a license';
  useEffect(() => {
    if (!approved) return;
    let alive = true, running = false;
    async function refresh() {
      if (running) return;
      running = true;
      try { const value = await currentApi.current('/api/devices/' + device.id); if (alive) {setLive(value); setError('');} }
      catch (e) { if (alive) setError(e.message); }
      finally { running = false; }
    }
    refresh(); const timer = setInterval(refresh, 3000);
    return () => {alive = false; clearInterval(timer);};
  }, [approved, device.id]);
  async function approve(event) {
    event.preventDefault();
    if (!candidates[Number(identity)] || identity === '' || !selected || issue || reason.trim().length < 5) return;
    setBusy(true); setError('');
    try {
      await api(`/api/actions/devices/${device.id}/approve`, {method:'POST', body:JSON.stringify({
        ...candidates[Number(identity)], license_id:selected.id, reason:reason.trim(), automatic_activation:true,
      })});
      setApproved(true); onApproved();
    } catch (e) {setError(e.message);} finally {setBusy(false);}
  }
  const active = approved && live.status === 'ACTIVE';
  return <div className="modal-overlay" onClick={() => {if (!busy) onClose();}}><section className="modal registration-flow" role="dialog" aria-modal="true" aria-labelledby="registration-flow-title" onClick={e => e.stopPropagation()}>
    <div className="modal-header"><div><span className="eyebrow">REGISTRATION FLOW</span><h2 id="registration-flow-title">{active ? 'Device active' : approved ? 'Approved — waiting for device' : 'Approve device'}</h2></div><button className="icon-button" aria-label="Close registration flow" disabled={busy} onClick={onClose}><X size={20}/></button></div>
    <ol className="registration-steps" aria-label="Registration flow">{['Requested','Approved','Active'].map((title,i) => <li key={title} className={i <= (active ? 2 : approved ? 1 : 0) ? 'done' : ''}><span>{i <= (active ? 2 : approved ? 1 : 0) ? <Check size={14}/> : i + 1}</span>{title}</li>)}</ol>
    {approved ? <><div className={active ? 'success-box' : 'notice'}>{active ? <><CheckCircle2/>The InfraBox is active.</> : 'Approval saved. The InfraBox will activate automatically on its next registration check, normally within five minutes. No token or extra approval is needed.'}</div>{active && <button className="button primary" onClick={onVpn}>Open VPN</button>}</> : <form onSubmit={approve}>
      <label>InfraBox<input readOnly value={device.serial}/></label>
      <label>License<select aria-label="License" value={licenseId} onChange={e => setLicenseId(e.target.value)}><option value="">Select a license</option>{licenses.map(l => {const why = licenseIssue(l,device,customers); return <option key={l.id} value={l.id} disabled={!!why}>{l.customer_name} · {l.kind}{why ? ' · '+why : ''}</option>;})}</select></label>
      {!eligible.length && <div className="notice">No available license. <button type="button" className="button" onClick={onManageLicenses}>Manage licenses</button></div>}
      <details open={identity === ''}><summary>Device identity</summary><label>Identity to approve<select aria-label="Identity to approve" value={identity} onChange={e => setIdentity(e.target.value)}><option value="">Select the identity on this InfraBox</option>{candidates.map((c,i) => <option key={i} value={i}>{c.installation_id}</option>)}</select></label>{identity !== '' && <code className="registration-key">{candidates[Number(identity)].public_key}</code>}</details>
      <label>Reason<textarea value={reason} onChange={e => setReason(e.target.value)} required minLength={5} maxLength={500} rows={3} placeholder="Why are you approving this InfraBox?" autoFocus/></label>
      <p className="muted">Approve once. This InfraBox activates automatically after proving its identity. VPN access is approved separately.</p>
      <div className="modal-actions"><button type="button" className="button" disabled={busy} onClick={onClose}>Cancel</button><button className="button primary" disabled={busy || identity === '' || !!issue || reason.trim().length < 5}>{busy ? <LoaderCircle className="spin" size={17}/> : <Check size={17}/>}Approve</button></div>
    </form>}
    {error && <div className="inline-error" role="alert">{error}</div>}{approved && <div className="modal-actions"><button className="button" onClick={onClose}>Close</button></div>}
  </section></div>;
}
