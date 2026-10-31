# Security assumptions and limits

This is the first production-oriented foundation, deployed initially in an isolated
HTTP lab. Production qualification requires HTTPS, operational review, independent
security review, monitoring, backups and device-side integration. HTTP lab mode is
explicit and defaults off. Never expose lab HTTP or tokens over the public Internet.

## Identity and clone limits

Ed25519 signatures prove possession of a private key, not physical Raspberry Pi
ownership. UUID and serial alone never authorize an installation. The device agent
reads the serial from the OS on every invocation; the server binds proofs to that
reported serial, installation, key, purpose, audience, nonce and expiry.

A copied SD card includes the software private key. A different honestly reported
serial is detected, audited and denied without poisoning the original device.
A malicious clone that spoofs the original serial and copies the key cannot be
reliably distinguished without hardware-backed keys/attestation. Simultaneous
activity is audit evidence, not hardware proof. The simulator intentionally permits
serial overrides for test identities; a production agent must not expose that option.
New identities on known serials remain pending; the serial does not grant recovery.

## Offline authorization

Only an already activated identity with a server-signed ACTIVE document can use
cached grace, default 24 hours and at most seven days by configuration. Grace
expires no later than the license. The public signing key must be provisioned/pinned
out of band; never download and trust a new key from the same unauthenticated HTTP
request. The simulator verifies signature, audience, version, status, serial, UUID,
public-key digest, issue/expiry timestamps and observed clock rollback.

A reachable server denial invalidates the simulator cache; only transport connection
failures/timeouts can fall back. A new device, absent/expired cache or locally known
revoked identity remains unauthorized when the server is unavailable. Server-side
revocation cannot invalidate an already issued document on a disconnected device
until expiry. Full SD-card rollback and a maliciously changed clock can bypass
software-only rollback bookkeeping; use trusted time/hardware and shorter grace
where required. Client software enforcement itself is not tamper-proof.

## Credentials and access

- Separate server signing key, device identity keys and bearer API tokens; no VPN
  key reuse. Private device keys never enter server requests.
- Administrator tokens contain 384 bits of randomness, are stored as SHA-256 hashes,
  expire after 90 days, and carry `admin` or read-only `viewer` roles. Bootstrap is
  local root only; no default password or unauthenticated admin setup endpoint.
- Activation tokens are random, hashed, expire, and bind device + installation + key
  + license. They never appear in logs. An authenticated retry with fresh proof is
  idempotent only for the original live binding.
- Device bearer sessions expire after five minutes and recheck the current binding
  and license on use. Suspension/revocation stops issuing authorization immediately.
- Source is root-owned; service runs non-root. PostgreSQL listens on loopback only;
  firewall allows API access only from the existing Caddy VM.
- SELinux/firewalld remain enabled. The installer never changes Caddy or another VM.
- Request body is bounded at 16 KiB, including chunked bodies. Proxy headers are
  ignored. Structured HTTP logs contain path/status/request ID, not bodies/headers.
- Database audit logs record administrative mutations and registration/security
  events. Database owners can alter them; ship copies to append-only external storage
  before relying on them as tamper-evident records.

## Operational scope

Use exactly one Uvicorn worker: the initial rate limiter is process-local, keyed to
the TCP client address and resets on restart. Behind Caddy all requests share its
budget (120/minute by default). Do not trust arbitrary X-Forwarded-For. Before scaling,
add a shared rate limiter and trusted proxy configuration. Authentication state,
proof replay protection and capacity locking are in PostgreSQL and survive restarts.
The global short transaction lock trades throughput for simple correctness; review
lock contention before a fleet rollout. Apply reverse-proxy request/header/time limits
in a separately authorized Caddy change before production.

Schema migrations and source upgrades are administrator operations. Never downgrade
or restore production data automatically. The service does not automatically activate
physical appliances or enforce licensing in the existing KVM application yet.
