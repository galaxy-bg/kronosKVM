# Proposed administrator password recovery

Status: deferred; use the installed host-only `infrabox-reset-admin` command.
The challenge/token flow below is design only. The CLI commands and recovery endpoints below are not yet
implemented. The current supported recovery remains the host-access procedure
in [web authentication](web-authentication.md).

## Recommended flow: host-issued recovery code

1. The login page's **Forgot password** link opens a recovery form. Opening the
   form does not change the password or revoke any session.
2. An operator signs in to the appliance through its host SSH account or physical
   console and runs the proposed `sudo kronoskvm auth recovery-code` command.
3. The CLI requests a cryptographically random, single-use recovery code from the
   API through a root-authorized local channel. The code is displayed once in
   the terminal. It must not be passed as a shell argument, written to logs, or
   exposed through an unauthenticated HTTP endpoint.
4. The operator enters that code in the HTTPS recovery form together with a new
   password and its confirmation. A successful submission directly sets a new
   password; it does not restore the known `ChangeMe` password.
5. Success consumes the code, revokes other recovery codes and all existing web
   sessions, closes active consoles through the existing revocation mechanism,
   and returns the operator to normal sign in. No automatic login occurs.

Codes expire after ten minutes. Store only their hashes and expiry in the API's
RAM; restarting the API invalidates them. Generating a new code invalidates the
previous one. Limit failed verification attempts and issuance, without allowing
unauthenticated visitors to invalidate a code or lock the administrator account.
Failed/expired-code submissions never change the current password.

Issuance must verify host-administrator authority independently of browser
sessions. Use a root-only Unix socket or another explicit local authorization
channel; a request being sent to localhost is insufficient authorization.
Persist only the salted hash of the final new password using the existing atomic
0600 credentials file. Record recovery events, never codes or passwords.

## Optional support-request challenge

For an operator/support workflow, the browser can additionally show a request
identifier. The host CLI may display and approve a specific pending identifier
before issuing a recovery code. The identifier is public correlation data, not
proof of identity or a password-reset credential. CLI/root authorization remains
mandatory. Bound pending requests in RAM, apply rate limits and expire them.

This extra step is useful for identifying a customer's request but unnecessary
when the same administrator owns the browser and host SSH session.

## Emergency host reset

The implemented `sudo /usr/local/sbin/infrabox-reset-admin` command restores
`admin` / `ChangeMe` with optional password replacement and immediate session
invalidation. It requires host root access and a `RESET` confirmation (or `--yes`).
Because the default password is publicly known, use this only with trusted local management access.
Prefer directly entering a new password through a hidden CLI prompt when web
access is unavailable. Do not enable default-password resets from anonymous web
requests.

## Required validation before implementation is deployed

Verify expiry, single use, invalidation after success/restart, bounded rate limits,
root-only issuance, no change on failed attempts, atomic password persistence,
session/WebSocket revocation, and absence of secrets in logs and shell arguments.
Also exercise the HTTPS browser flow and ensure another visitor cannot consume
or invalidate an operator's recovery request.
