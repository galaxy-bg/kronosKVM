# Security Policy

KDX InfraBox is not production-ready. Do not expose it to untrusted networks.

Report vulnerabilities privately to the KronosDX project owner. Do not include
passwords, tokens, private keys, private inventory reports or customer data.

The API binds to localhost behind the management gateway. Privileged hardware
actions use allow-listed host helpers; arbitrary shell endpoints are prohibited.
HTTPS and single-admin web authentication are implemented. Changing the default
password is optional; multiple users and roles remain pending.
See [web authentication](docs/web-authentication.md) for session and recovery policy.
Remote Assist supplies VPN connectivity; web authentication also applies over VPN.
