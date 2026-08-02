# systemd

The active appliance uses `kronoskvm-containers.service` to start the API and
web containers. The API binds only inside the Compose network; the web gateway
publishes the management application on Ethernet and the appliance AP.

`kronoskvm-usb-gadget.service` configures the USB-C keyboard and relative-mouse
gadget after boot. `kronoskvm-power-action.path` watches the API's constrained
request file and delegates validated reboot or power-off actions to a root-only
helper. See the unit files in this directory for ordering and hardening details.
