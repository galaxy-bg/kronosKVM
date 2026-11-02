# Registration approval and activation

Dashboard registration now has four steps: verify the serial and public identity,
select the customer/license, review approval, and wait for actual device activation.
VPN permission remains a separate administrator action.

The review step explicitly offers **Automatically activate when this device next
proves its identity**, selected by default in the new workflow. This creates an
expiring approval bound to that exact device, installation, Ed25519 key and license.
It does not immediately mark the device ACTIVE. The existing agent's next signed
authentication consumes the approval and activates the binding. The normal agent
timer runs every five minutes; an operator can trigger its service for an immediate
check. The workflow polls inventory and shows success only after the device is ACTIVE.

The server rechecks customer, license validity/capacity and device state at activation.
A PostgreSQL license-row lock serializes capacity checks. New approval supersedes
older unconsumed approvals for that device. A different installation/key or license
binding still requires explicit recovery/reassignment. An offline device must connect
within the one-hour approval window or receive a fresh approval.

Manual token activation remains available by clearing the automatic option. The API
defaults `automatic_activation` to false for compatibility; old approvals stay manual
after migration. For a device waiting for a missing token, review it again through
the new workflow and explicitly approve automatic activation. Do not edit database
approval flags or mark a device ACTIVE manually.

The license step explains full, inactive and expired licenses and blocks their
selection. It links to license management when no eligible license exists. Approval
does not grant VPN access or change license capacity.

## Deployment

Back up PostgreSQL, registration source and dashboard assets. Install migration
`0006_automatic_activation.py` and run `alembic upgrade head` before restarting the
updated registration application. Publish the dashboard build using
`dashboard/deploy/publish_static.py`. Agent and appliance images need no update.
Rollback application code first; keep the additive column until newer approvals
are resolved. The migration defaults pre-existing rows to manual activation.

Tests cover signed activation, invalid proofs, installation isolation, expired
approval/license, suspension, capacity changes and retirement of old manual tokens.
Browser checks cover all four steps, full-license rejection, mobile layout and the
distinction between approval accepted and device actually activated.
