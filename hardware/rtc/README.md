# RTC and Power

The final RTC/power board is pending. The prototype currently receives power
through a GPIO-connected supply so USB-C can be used for the KVM HID gadget.
The production board must isolate target-side USB VBUS and provide safe boot,
reboot and shutdown sequencing; an RTC function alone does not provide this.
