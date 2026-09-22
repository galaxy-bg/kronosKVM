# Product naming

The current product name is **KDX InfraBox**, developed by **KronosDX**.
The product descriptor is **Infrastructure in a Box**. Use this naming in
current documentation, screenshots, packaging and user-facing descriptions.

| Context | Name |
|---|---|
| Product | KDX InfraBox |
| Vendor | KronosDX |
| GitHub repository | `galaxy-bg/kronosKVM` (historical project identifier) |
| Python package | `kronoskvm` |
| Existing services/containers | `kronoskvm-*` |
| Installed source | `/opt/kronoskvm` |
| Configuration and state | `/etc/kronoskvm`, `/var/lib/kronoskvm` |
| Current management AP SSID | `KronosDX-iKVM` |

The repository has not been renamed. Existing package names, filesystem paths,
API identifiers, service units and network profiles remain compatible with
installed appliances. Their presence does not mean the product is still
marketed as KronosKVM. A technical rename would require a separate migration.

Historical changelog entries, the implementation log and retired CM4 inventory
retain the names and addresses used at the time. Current entry-point documents
use KDX InfraBox and link to the active Raspberry Pi 4 design.

Product naming does not establish production readiness. The current appliance
has verified KVM/storage/recovery and WireGuard access paths, while clean-OS
reproducibility, per-user authentication and final hardware qualification remain
separate milestones.
