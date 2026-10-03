# Security Design

- Credentials, private keys and inventory artifacts are never committed.
- Development services bind to loopback.
- Production web access requires HTTPS, authentication and session controls.
- Optional ports remain disabled by default.
- The API never exposes arbitrary shell commands.
- Privileged hardware actions use minimal, allow-listed helpers.
- Services run as dedicated non-root users with systemd hardening.
- Configuration changes require backups, idempotence and explicit approval.
- ETH0 is the normal update/deployment path; the isolated AP is preserved as
  an independent recovery path.
- ETH0 and Wi-Fi changes are never made in the same transaction.
- Network configuration is validated before reboot and a second management
  path is verified before restarting either network side.
- Operational status output must never read or display passphrases, passwords,
  tokens, proxy credentials or private keys.

## SSH management switch

Services → SSH Management provides confirmed Start/Stop actions. Stop disables
both `ssh.socket` and `ssh.service`, including boot activation. Start leaves
socket activation disabled and enables/starts `ssh.service`. Existing SSH sessions
may survive Stop (`KillMode=process`); it blocks new logins, not session revocation.
The web management plane and Remote Assist remain available to re-enable SSH.
This switch does not replace management-network access controls or web authentication.
