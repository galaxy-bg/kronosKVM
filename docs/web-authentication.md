# Web administrator authentication

The management UI requires HTTPS and an administrator session. On a fresh
installation, sign in with `admin` / `ChangeMe`. Password replacement is optional;
the default account can open the dashboard immediately. If changed, the new
password must have at least 12 characters. A shared default password is not a
zero-trust access policy and does not restrict host OS access.

Use the **admin** button to change the password later, or **Sign out** to end the
session. Password changes revoke all previous sessions. Open consoles are
revoked within five seconds of logout or password change. Sessions expire after
30 minutes without authenticated requests and after eight hours in total.
Automatic UI polling counts as activity. Restarting the API signs out everyone.

The browser uses a host-only Secure, HttpOnly, SameSite=Strict cookie. Mutation
requests require `X-InfraBox-Request: 1`; supplied Origin headers must match the
HTTPS host. WebSocket requests require a matching Origin. Requests over HTTP
are redirected to HTTPS by Nginx. Only API `/api/v1/health` and gateway `/healthz`
are public health checks; documentation and management APIs require a session.
The login/session endpoints remain accessible before authentication.

Passwords are stored as salted scrypt hashes in `/state/web-auth.json`, mounted
from `/var/lib/kronoskvm/state/web-auth.json`, with file mode 0600. This file is
written on the first successful login and password changes only. Sessions,
last-activity timestamps and login throttling are held in RAM. Five login
attempts per client or 30 across clients in one minute trigger rate limiting.
The API is intended to run as a single worker, as in the current container.

For local development, set `KRONOSKVM_AUTH_PATH` to a writable private file and
serve the gateway over HTTPS. Do not disable authentication to deploy a gateway.
Existing endpoint unit tests isolate their business logic from the perimeter;
`backend/tests/test_auth.py` exercises the real middleware and session lifecycle.

## Recovery with host access

If the password is lost, the appliance owner connects through SSH or the local
host console and runs:

```sh
sudo /usr/local/sbin/infrabox-reset-admin
```

Type `RESET` when prompted. The command stops the API, atomically restores the
`admin` / `ChangeMe` credentials, and starts the API again. All web sessions and
consoles are disconnected; other containers and host SSH accounts are unchanged.
Password replacement remains optional. The command requires host root privileges;
there is no anonymous web reset endpoint. A reset event is logged without secrets.
For an explicitly confirmed noninteractive operation, append `--yes`.

The customer's web password is independent of the owner's SSH credentials. Keep
host SSH credentials private. This workflow does not add customer/owner web roles
or alter SSH access policy. Only run the command when a reset is actually wanted;
installing the helper does not reset the existing password.

## Scope

This is one local administrator, not a multi-user role system. SSH host accounts,
WireGuard peers, and HTTP/FTP/TFTP Recovery downloads retain their own access
policies. Management authentication does not authenticate those download
services. The management AP's wireless access policy also remains separate.
Long-running downloads and transfers already accepted may finish after logout;
new API requests and console activity are denied.
