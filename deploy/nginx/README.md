# Nginx

The development gateway listens only on `192.168.34.100:80`, serves the static
frontend and proxies `/api/` to the localhost FastAPI service.

It must not bind to ETH0. HTTPS and authentication remain pending.
