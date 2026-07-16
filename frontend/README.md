# Frontend

The initial development dashboard is served only on the isolated management AP:

```text
http://192.168.34.100
```

It uses same-origin `/api/` requests through the web gateway. Authentication and
HTTPS remain required before production or customer-network exposure.
