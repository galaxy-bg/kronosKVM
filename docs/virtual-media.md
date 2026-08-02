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

Presenting a staged ISO/IMG to the target as USB mass storage is not implemented
yet. The eventual gadget function must default to read-only and provide safe
attach/detach behavior without destabilizing keyboard and mouse endpoints.
