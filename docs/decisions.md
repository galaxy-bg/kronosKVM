# Decisions

## D-001 — Temporary proprietary license

KronosDX retains all rights until an explicit permanent license is selected.

## D-002 — Independent architecture

PiKVM may be studied as a technical reference, but KronosKVM keeps independent
identity, configuration, API, service layout, hardware abstraction and UI.

## D-003 — FastAPI control plane

Use typed Python, FastAPI, Pydantic and YAML with localhost-only development
binding.

## D-004 — Public repository

The operator explicitly selected a public GitHub repository, overriding the
earlier private-repository proposal.

## D-005 — Hybrid container architecture

Containerize the application plane from early development. Keep network, USB
gadget, boot configuration and privileged hardware helpers on the host. Do not
grant containers blanket privilege or Docker socket access.
