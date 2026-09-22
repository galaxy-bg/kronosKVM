# Security Policy

KDX InfraBox is not production-ready. Do not expose it to untrusted networks.

Report vulnerabilities privately to the KronosDX project owner. Do not include
passwords, tokens, private keys, private inventory reports or customer data.

The API binds to localhost behind the management gateway. Privileged hardware
actions use allow-listed host helpers; arbitrary shell endpoints are prohibited.
HTTPS is implemented, but per-user web authentication is still pending.
Remote Assist supplies VPN connectivity and does not add web authentication.
