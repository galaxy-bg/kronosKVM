import React, {useEffect, useRef, useState} from 'react';
import {Check, CheckCircle2, ChevronRight, LoaderCircle, X} from 'lucide-react';
import './registration-flow.css';

const steps = ['Verify identity', 'Customer and license', 'Review approval', 'Device activation'];

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
  const [step, setStep] = useState(0);
  const [identity, setIdentity] = useState(candidates.length === 1 ? '0' : '');
  const [customer, setCustomer] = useState(device.customer_id || '');
  const [licenseId, setLicenseId] = useState('');
  const [reason, setReason] = useState('');
  const [automatic, setAutomatic] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [live, setLive] = useState(device);
  const currentApi = useRef(api); currentApi.current = api;
  const selected = licenses.find(l => l.id === licenseId);
  const available = licenses.filter(l => l.customer_id === customer && !licenseIssue(l, device, customers));
  const issue = selected ? licenseIssue(selected, device, customers) : 'Select a license';

  useEffect(() => {
    if (step !== 3) return;
    let alive = true, running = false;
    async function refresh() {
      if (running) return;
      running = true;
      try {
        const value = await currentApi.current('/api/devices/' + device.id);
        if (alive) { setLive(value); setError(''); }
      } catch (e) { if (alive) setError(e.message); }
      finally { running = false; }
    }
    refresh(); const timer = setInterval(refresh, 3000);
    return () => { alive = false; clearInterval(timer); };
  }, [step, device.id]);

  async function approve() {
    if (!candidates[Number(identity)] || !selected || issue || reason.trim().length < 5) return;
    setBusy(true); setError('');
    try {
      const value = await api(`/api/actions/devices/${device.id}/approve`, {method: 'POST', body: JSON.stringify({
        ...candidates[Number(identity)], license_id: selected.id, reason: reason.trim(),
        token_ttl_seconds: 3600, automatic_activation: automatic,
      })});
      setResult(value); setStep(3); onApproved();
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  function next() {
    setError('');
    if (step === 0 && identity !== '') setStep(1);
    else if (step === 1 && selected && !issue) setStep(2);
  }
  const active = live.status === 'ACTIVE';
  return <div className="modal-overlay" onClick={() => { if (!busy) onClose(); }}>
    <section className="modal registration-flow" role="dialog" aria-modal="true" aria-labelledby="registration-flow-title" onClick={e => e.stopPropagation()}>
      <div className="modal-header"><div><span className="eyebrow">REGISTRATION WORKFLOW</span><h2 id="registration-flow-title">{step === 3 ? active ? 'Device activated' : 'Waiting for device activation' : 'Approve device registration'}</h2></div><button className="icon-button" aria-label="Close registration workflow" disabled={busy} onClick={onClose}><X size={20}/></button></div>
      <ol className="registration-steps" aria-label="Registration progress">{steps.map((title, i) => <li key={title} className={i === step ? 'current' : i < step ? 'done' : ''} aria-current={i === step ? 'step' : undefined}><span>{i < step ? <Check size={14}/> : i + 1}</span>{title}</li>)}</ol>
      {step === 0 && <>
        <p>Verify this serial and public key against the physical InfraBox before granting access.</p>
        <label>Hardware serial number<input readOnly value={device.serial}/></label>
        <label>Identity to approve<select aria-label="Identity to approve" value={identity} onChange={e => setIdentity(e.target.value)}><option value="">Select installation and public key</option>{candidates.map((c, i) => <option key={i} value={i}>{c.installation_id} · {c.public_key.slice(0, 10)}…</option>)}</select></label>
        {identity !== '' && <div className="registration-key"><small>Ed25519 public key</small><code>{candidates[Number(identity)].public_key}</code></div>}
        {!candidates.length && <div className="inline-error">The device must connect and register its identity before approval.</div>}
      </>}
      {step === 1 && <>
        <label>Customer<select aria-label="Customer" value={customer} onChange={e => {setCustomer(e.target.value); setLicenseId('');}}><option value="">Select a customer</option>{customers.filter(c => !c.archived_at).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
        <label>License / customer<select aria-label="License / customer" value={licenseId} onChange={e => setLicenseId(e.target.value)}><option value="">Select a license</option>{licenses.filter(l => l.customer_id === customer).map(l => {const why = licenseIssue(l, device, customers); return <option key={l.id} value={l.id} disabled={!!why}>{l.kind} · {l.used_devices}/{l.max_devices} devices{why ? ' · ' + why : ' · Available'}</option>;})}</select></label>
        {customer && !available.length && <div className="notice">This customer has no eligible license. Create a license with an available device slot to continue.</div>}
        <button type="button" className="button" onClick={onManageLicenses}>Manage or create licenses</button>
      </>}
      {step === 2 && <>
        <dl className="registration-review"><dt>InfraBox</dt><dd>{device.serial}</dd><dt>Customer</dt><dd>{customers.find(c => c.id === customer)?.name}</dd><dt>License</dt><dd>{selected?.kind} · {selected?.used_devices}/{selected?.max_devices} devices</dd></dl>
        <label className="registration-option"><input type="checkbox" checked={automatic} onChange={e => setAutomatic(e.target.checked)}/><span>Automatically activate when this device next proves its identity</span></label>
        <p className="muted">{automatic ? 'Approval binds this installation and public key to the selected license. The device must make a fresh signed connection within one hour. VPN permission is approved separately.' : 'A single-use activation token will be shown. Transfer it securely to the device activation command; approval alone will not activate the device.'}</p>
        <label>Reason for approval<textarea value={reason} onChange={e => setReason(e.target.value)} minLength={5} maxLength={500} rows={3} placeholder="How did you verify the identity and customer?"/></label>
      </>}
      {step === 3 && <>
        {active ? <div className="success-box"><CheckCircle2/>The device proved its identity and its registration is active.</div> : <div className="notice">{result?.automatic_activation ? 'Approval saved. The InfraBox will activate on its next signed registration check, normally within five minutes. Keep its internet connection available. No token transfer is needed.' : 'Approval saved. Complete the activation command on the InfraBox using the token below.'}</div>}
        <dl className="registration-review"><dt>Serial</dt><dd>{device.serial}</dd><dt>Current status</dt><dd role="status">{live.status === 'ACTIVE' ? 'Active' : 'Awaiting activation'}</dd></dl>
        {result?.activation_token && <><label>Single-use activation token<textarea readOnly value={result.activation_token} rows={3}/></label><p className="muted">Shown only in this dialog. Expires after one hour. On the InfraBox, run <code>sudo -u kdx-registration python3 /opt/kdx-registration-client/client.py activate</code> and enter the token at the prompt.</p></>}
        {!active && <p className="muted">This screen waits for actual device activation. Repeating approval is not necessary. If the device stays offline for an hour, review and issue a new approval.</p>}
        {active && <button className="button primary" onClick={onVpn}>Continue to VPN approval<ChevronRight size={17}/></button>}
      </>}
      {error && <div className="inline-error" role="alert">{error}</div>}
      <div className="modal-actions"><button className="button" disabled={busy} onClick={onClose}>{step === 3 ? 'Close' : 'Cancel'}</button>{step > 0 && step < 3 && <button className="button" disabled={busy} onClick={() => setStep(step - 1)}>Back</button>}{step < 2 && <button className="button primary" onClick={next} disabled={step === 0 ? identity === '' : !selected || !!issue}>Continue<ChevronRight size={17}/></button>}{step === 2 && <button className="button primary" disabled={busy || reason.trim().length < 5 || !!issue} onClick={approve}>{busy ? <LoaderCircle className="spin" size={17}/> : <Check size={17}/>}Approve registration</button>}</div>
    </section>
  </div>;
}
