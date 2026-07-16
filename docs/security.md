# Security Design

- Credentials, private keys and inventory artifacts are never committed.
- Development services bind to loopback.
- Production web access requires HTTPS, authentication and session controls.
- Optional ports remain disabled by default.
- The API never exposes arbitrary shell commands.
- Privileged hardware actions use minimal, allow-listed helpers.
- Services run as dedicated non-root users with systemd hardening.
- Configuration changes require backups, idempotence and explicit approval.
