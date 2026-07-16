# systemd

`kronoskvm-api.service` runs the FastAPI control plane as the locked
`kronoskvm` account. It binds only to `127.0.0.1:8000` and applies baseline
systemd hardening.

Capture, HID, virtual-media and serial units remain unimplemented and disabled.
