# Video Capture

HDMI capture is inactive. HDMI0/HDMI1 appear to be CM4 display outputs. Target
video is expected to arrive through an HDMI-to-CSI bridge on CAM0. Do not add
overlays or edit boot configuration until capture hardware is installed and
identified. The first inventory found only BCM2835 codec/ISP and RPivid nodes;
there was no `/dev/video0` capture device and no detected camera interface.
