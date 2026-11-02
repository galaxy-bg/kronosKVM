# Simple registration flow

The dashboard uses one approval form: license, reason, **Approve**. When exactly
one eligible license is available it is selected automatically. The latest
signed device identity is selected when unambiguous; identity details remain
available for verification. Full, expired or inactive licenses cannot be selected.

Progress reads **Requested → Approved → Active**. Approval activates the exact
identity on its next signed device check, normally within five minutes. There
is no activation checkbox or token transfer in this flow. The screen waits for
actual ACTIVE status rather than treating acceptance as activation.

The approval API now defaults `automatic_activation` to true, so cached versions
of the original approval form behave the same way. Explicit false is retained
only for integrations that intentionally use manual token activation. Migration
0006 preserves existing approvals as manual; new approvals supersede unused old
approvals. License validity/capacity and device state are rechecked at activation.

For a fresh setup, delete VPN through its synchronized deletion workflow first,
then use registration recovery/reassignment. Preserve audit history, expire old
approvals and release only that device's license binding. Back up private state
before generating a new installation/key on the appliance. Re-enroll, then approve
the fresh device identity. Other devices and license capacity remain unchanged.

VPN approval is separate from registration approval. No device is marked ACTIVE
by directly editing its database status or approval flags.

## Deployment

Back up PostgreSQL and both application trees. Migration 0006 must already be
installed. Update registration main/schema and restart registration, then publish
the matching dashboard build with `dashboard/deploy/publish_static.py`. Existing
agent and appliance images need no update. Explicit manual API clients should
send `automatic_activation: false`.

Tests cover plain approval defaults, signed activation, invalid proofs, identity
isolation, expired approvals/licenses, suspension, capacity, and old-token retirement.
Browser tests cover the single form, mobile layout, full-license rejection and
waiting for actual activation.
