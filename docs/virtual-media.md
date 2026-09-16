# Virtual Media and Staging

The appliance exposes a 32 GiB logical staging pool on the internal 64 GB
microSD filesystem. It does not require a separate partition.

The UI supports:

- file chooser and drag-and-drop upload
- ISO, IMG, firmware, archive and appliance-image filters
- two concurrent browser uploads
- background task progress, cancellation and completion state
- download and delete
- cleanup of partial `.uploading` fragments on failure, cancellation and API start

The staging API reserves 10 GiB for the operating system and caps managed files
at 32 GiB. A future external USB drive may extend the pool through the assigned
blue USB 3.0 storage port.

ISO and IMG files can be attached from Storage or the KVM Virtual Media drawer.
The host helper validates that the file remains inside managed staging storage,
then inserts it into the permanently configured mass-storage LUN:

- Small ISO images are exposed as a read-only removable CD-ROM.
- Linux's gadget CD-ROM mode truncates images at 1,152,000 sectors (about
  2.36 GB). At or above this limit, ISOs with a disk partition table are exposed
  as a read-only removable disk. Choose **UEFI USB / USB HDD** in the target's
  boot menu for these hybrid images, including recent Ubuntu desktop ISOs.
  Oversized ISOs without a disk partition table are rejected before changing
  the current media; use a hybrid ISO or bootable IMG instead.
- IMG files are exposed as a read-only removable disk.
- Eject clears the LUN without rebuilding the keyboard/mouse gadget.
- Mounted media cannot be deleted until it is ejected.

If mount/eject requests stop being processed, open **Services → Virtual Media
(ISO/IMG) → Restart** to restart the action watcher. **View Logs** includes both
the watcher and the mount/eject helper logs.

For firmware transfers over the service port, see [Recovery services](recovery-services.md).

Virtual media activity is shown in Storage and the KVM console. The host samples
`file-storage`'s `rchar` counter about every five seconds, including reads served
from cache. The indicator shows Reading (with sampled bytes/second), Idle, USB
disconnected, or Activity unavailable, plus the last observed read time. It is
not installation progress or a guarantee of successful boot. Idle alone is not
an error. Samples older than 20 seconds are unavailable, and a changed mount or
reset counter starts a new baseline. Multiple mass-storage workers are treated
as unavailable because their reads cannot safely be attributed to this gadget.

If the target locks the medium and normal Eject returns “Device or resource busy”,
stop its installation and use **Force Eject** in the Storage summary or the KVM
Virtual media drawer. Confirming bypasses the target's media-removal lock using
configfs `forced_eject`; it does not reboot the appliance or reset the HID gadget.
Mount the desired image afterward. The button remains available if the old image
was deleted. Failed operations retain the actual backing filename so deletion,
publication and overwrite remain blocked until the medium is released.
