# Architecture

KronosKVM is an independent modular appliance. PiKVM is a technical reference,
not a source-tree template.

Planned services:

- `kronoskvm-api`: coordination and versioned API
- `kronoskvm-web`: browser interface
- `kronoskvm-capture`: HDMI-to-CSI capture and streaming
- `kronoskvm-hid`: keyboard and mouse gadget control
- `kronoskvm-virtual-media`: read-only-first image attachment
- `kronoskvm-serial`: serial discovery and locked sessions
- `kronoskvm-network`: explicit network-mode management
- `kronoskvm-display`: optional local touchscreen
- `kronoskvm-health`: device and service monitoring

Hardware adapters are optional and expose explicit state. Missing hardware must
not stop the control plane. Privileged operations will live behind narrow,
audited helpers rather than arbitrary command execution.
