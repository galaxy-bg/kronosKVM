# Development Plan

1. Repository and documentation.
2. Safe, read-only system discovery.
3. Base OS preparation: dedicated account, filesystem layout, persistent logs
   and time validation. Package/firewall work waits for the OS baseline and
   physical interface mapping.
4. Localhost FastAPI health and capability service. Completed for read-only
   system, network, storage, service and optional-hardware discovery.
5. Serial-console support.
6. Verified USB HID gadget.
7. HDMI-to-CSI capture.
8. Read-only-first virtual media.
9. Authenticated web interface and HTTPS.
10. Portable Wi-Fi and local touchscreen operation.
11. KDX Genesis integration.

Each milestone ends with tests, a risk review and explicit approval before
system-changing work.
