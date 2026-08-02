# KronosKVM logging

KronosKVM writes structured JSON application and audit events to both:

- `/var/log/kronoskvm/application.jsonl`
- the `kronoskvm-api` container's journald stream

The file rotates at 10 MiB and keeps five backups. The system journal is
persistent, capped at 256 MiB, and retained for up to 14 days.

## Recorded events

- Every HTTP request, including status, duration and request ID
- Mutating API calls (`POST`, `PUT`, `PATCH`, `DELETE`)
- SSH session start, failure and end metadata
- Serial console start, rejection, end and byte counters
- HID/KVM session start, end and report counters
- Container, systemd, kernel, USB and network service messages in journald

Passwords, keyboard keys and terminal payloads are not written to the audit
log. An operator can explicitly capture a terminal transcript with the terminal
window's **Start log** action and download it locally.

## Useful commands

```bash
sudo tail -f /var/log/kronoskvm/application.jsonl
sudo journalctl CONTAINER_NAME=kronoskvm-api -f
sudo journalctl -u kronoskvm-containers -f
sudo journalctl -u ssh -u NetworkManager -u dnsmasq --since today
sudo journalctl -k --since today
```

Filter audit events with `jq`:

```bash
sudo jq -c 'select(.logger == "kronoskvm.audit")' \
  /var/log/kronoskvm/application.jsonl
```
