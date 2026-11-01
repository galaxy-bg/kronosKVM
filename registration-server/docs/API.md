# API contract

Interactive documentation: `/docs`; machine-readable schema: `/openapi.json`.
All JSON bodies reject extra fields. UUIDs are canonical, Pi serials contain exactly
16 hexadecimal characters and normalize uppercase. Public keys are base64 of 32 raw
Ed25519 bytes; signatures are base64 of 64 raw bytes.

## Device endpoints

| Method/path | Input / authentication | Result |
| --- | --- | --- |
| `GET /health` | None | Database liveness, service/version |
| `POST /api/v1/devices/enroll` | serial, installation_id, public_key, model, firmware | device_id, installation_id, PENDING/status, informational SSID |
| `POST /api/v1/devices/challenge` | serial, installation_id, public_key, purpose (`authenticate` or `activate`) | challenge_id, exact message, expires_at |
| `POST /api/v1/devices/verify` | challenge_id, signature | authorization status; document and session_token only if ACTIVE |
| `POST /api/v1/devices/activate` | challenge_id, signature, activation_token | Bound activation/status/document/session |
| `GET /api/v1/devices/status` | Bearer device session | Current identity/license status |
| `POST /api/v1/devices/heartbeat` | Bearer device session | Current status; refreshed signed document/session if ACTIVE |

Sign the returned `message` string exactly, UTF-8 encoded. Never reconstruct JSON
or send a private key. Challenge lifetime defaults to 120 seconds; a challenge can
be attempted once, including a failed signature/purpose attempt. Use a new challenge
for a retry. The signed challenge includes a random nonce, server audience, purpose,
serial, installation UUID, public-key digest and expiry.

ACTIVE responses contain `authorization: {payload, signature}`. Verify signature over
canonical JSON (sorted keys, compact separators, ASCII escaping) with the pinned
server Ed25519 public key. Payload includes device/license IDs, hardware/installation/
key bindings, audience, issue time and expiry. See the simulator implementation.
Session tokens and activation tokens are secrets and must not be included in URLs.

`HARDWARE_MISMATCH` is a 403 error detail and registration event for the attempted
clone; the original device retains its state. A different UUID/key on known serial
appears as a pending installation in the existing device detail.

## Administrator endpoints

All require `Authorization: Bearer <administrator-token>`. `viewer` can read;
`admin` can mutate. No unauthenticated token-issuance endpoint exists.

| Method/path | Body / result |
| --- | --- |
| `POST /api/v1/admin/customers` | `{name}` → customer ID |
| `POST /api/v1/admin/licenses` | `{customer_id,kind,max_devices,expires_at?}` → license ID |
| `GET /api/v1/admin/devices?offset=0&limit=100` | Device summaries; limit ≤200 |
| `GET /api/v1/admin/devices/{id}` | Summary, all installations/public keys, last 100 events |
| `POST /api/v1/admin/devices/{id}/approve` | `{installation_id,public_key,license_id,reason,token_ttl_seconds?}` → one-time activation token |
| `POST /api/v1/admin/devices/{id}/suspend` | `{reason}` |
| `POST /api/v1/admin/devices/{id}/revoke` | `{reason}` |
| `POST /api/v1/admin/devices/{id}/reassign` | `{reason}` → release current identity/license, invalidate unused tokens; explicit approval required afterward |
| `POST /api/v1/admin/licenses/{id}/renew` | `{reason,expires_at}`; timezone required |
| `POST /api/v1/admin/licenses/{id}/suspend` | `{reason}` |
| `POST /api/v1/admin/licenses/{id}/resume` | `{reason}`; revoked licenses cannot resume |
| `POST /api/v1/admin/licenses/{id}/revoke` | `{reason}`; issue new license to replace |

License kinds: PERPETUAL, SUBSCRIPTION, RENTAL, DEMO. All except PERPETUAL require
future expiration. `max_devices` is enforced against transactional device bindings,
including suspended devices until explicit release. A device has at most one license.

Recovery: enroll the replacement installation; review the inventory; `reassign` the
original device with a reason; `approve` the replacement installation/key/license;
activate using a new proof. The old installation stops authorizing. Hardware transfer:
explicitly `reassign` the old device, then approve an enrolled new device with that
license. Hardware serial bindings are immutable; original historical records remain.

Errors: 401 invalid credentials/proof/token, 403 hardware/key mismatch or forbidden
role, 404 missing record, 409 capacity/state conflict, 413 body too large, 422 invalid
input, 429 rate limit. Device denials and admin mutations are recorded in PostgreSQL.
A 5xx is not authorization. Clients must fail closed except for a previously verified,
unexpired signed grace document on a genuine transport outage.

## Dashboard read endpoints

Authenticated administrator/viewer GET endpoints added for Dashboard integration:

- `/api/v1/admin/session`: actor name, role and credential expiry; no bearer value/hash.
- `/api/v1/admin/customers?offset=0&limit=200`: customer IDs/names.
- `/api/v1/admin/licenses?offset=0&limit=200`: customer, kind, effective status,
  expiry, capacity and bound device IDs; no activation-token data.
- `/api/v1/admin/events?offset=0&limit=100`: paged audit actor/action/target/detail/time.

Device summaries additionally return nested `customer`, `license` and
`pending_installations`. The last field lists non-current installations that have
never completed activation. It allows a new SD installation on an active device to
appear in the Dashboard review queue without changing the original ACTIVE binding.

## Customer and device management

All writes below require an administrator. Unknown request fields are rejected.
Edits and archive/restore actions require a 5–500 character `reason`.

| Endpoint | Request / behavior |
| --- | --- |
| `POST /api/v1/admin/customers` | `name`, optional `contact_name`, `email`, `phone` |
| `PATCH /api/v1/admin/customers/{id}` | Same customer fields plus `reason`; changing email clears verification |
| `POST /api/v1/admin/customers/{id}/archive` | `reason`; rejects active licenses or active/suspended device associations |
| `POST /api/v1/admin/customers/{id}/restore` | `reason`; retains ID and history |
| `POST /api/v1/admin/devices` | `serial`, `model`, optional `display_name`, `notes`, `customer_id`; creates PENDING only |
| `PATCH /api/v1/admin/devices/{id}` | `display_name`, `notes`, `customer_id`, `reason`; serial/key immutable |
| `POST /api/v1/admin/devices/{id}/archive` | `reason`; requires stopping active authorization, revokes and expires unused activation tokens |
| `POST /api/v1/admin/devices/{id}/restore` | `reason`; restores visibility, retains revoked authorization |

PATCH requests represent the full editable metadata form: omitted optional fields
are cleared. A licensed device cannot change customer through metadata editing;
use controlled reassignment. Archived customers cannot receive new licenses.
Customers/devices lists accept `include_archived=true`, default false. Summaries
include `archived_at`; customers include contacts and `email_verified`; devices
include `display_name` and `notes`. Archival preserves bindings and audit records.

The same-origin dashboard gateway exposes create/edit paths under `/api/customers`
and `/api/devices`, with lifecycle actions under
`/api/actions/{customers|devices}/{id}/{archive|restore}`. Mutations require the
existing session, allowed Origin and CSRF token.

## Device-key VPN requests

`POST /api/v1/devices/challenge` additionally accepts purpose `vpn` with
`vpn_request` containing `{version:1,device_id,hostname,public_key,request_id}`.
Here `device_id` is the lowercase 16-digit hardware serial; the outer identity
uses its existing installation UUID and Ed25519 public key. The challenge binds
SHA-256 of the canonical VPN request and is single-use.

`POST /api/v1/devices/vpn` accepts `{challenge_id,signature,request}`. A valid
proof creates/reads a PENDING grant independently of licensing. An ACTIVE grant
returns a signed `kdx-infrabox-vpn` document with the exact public registration,
serial and a ten-minute validity window. Existing grants cannot be overwritten
with another installation/key/request. No VPN private key is transferred.

Administrators/viewers can `GET /api/v1/admin/vpn` (up to 200 records). Only
administrators can POST `/api/v1/admin/vpn/{id}/{approve|suspend|resume|archive}`
with `{reason}`. These actions use the constrained server key and audit the
operator, reason and device. Remote failures return 503 without reporting grant
success; retry the same action for reconciliation. Archive keeps the IP reserved
and requires operator recovery before a replacement grant.

See [central VPN deployment and acceptance](../../docs/central-vpn.md).

## Bidirectional VPN deletion

The current VPN delete protocol supersedes the earlier archive/restore behavior.
See [VPN deletion, retired generations and fresh setup](../../docs/vpn-deletion.md).
Administrator `/api/v1/admin/vpn/{id}/delete` removes the peer/registry entry and
frees the IP. Device proofs bind `vpn_operation` / `operation` (`sync` or `delete`).
Deleted generations receive a signed DELETED instruction; a fresh request/key
requires new approval. Deleted grants are hidden from the default list.

## Desktop VPN clients

`GET /api/v1/admin/vpn-clients` lists public client metadata and server permission
(up to 200 non-deleted records). Administrator POST to the same path accepts
`{id,name,platform,public_key,owner_name?,email?,customer_id?}`. `id` is a browser
UUID for safe retries; platform is WINDOWS, MACOS, LINUX or OTHER. No private key,
custom routes, server address or desired client IP may be supplied. The response
contains public registration metadata for local browser .conf rendering.

Administrator POST `/api/v1/admin/vpn-clients/{id}/{suspend|resume|delete}` requires
a reason. Deletion is idempotent, cannot be resumed, and releases the server IP.
There is no private-key download/export API. See [desktop VPN](../../docs/desktop-vpn.md).

## Live peer table deletion

Administrator POST `/api/v1/admin/vpn-peers/delete` accepts
`{public_key,allowed_ips,reason}` with exact canonical private IPv4 /32 selections.
Known device/desktop keys use the corresponding central deletion flow. Unknown
keys use constrained unmanaged-peer deletion; server-registered peers cannot
bypass their central lifecycle. See [peer actions](../../docs/vpn-peer-actions.md).
