from typing import Optional

from pydantic import BaseModel


class PhysicalPort(BaseModel):
    id: str
    name: str
    physical_label: str
    usb_path: Optional[str] = None
    connected: bool
    status: str
    device_name: Optional[str] = None
    vendor_id: Optional[str] = None
    product_id: Optional[str] = None
    serial_device: Optional[str] = None
    console_available: bool = False


class PhysicalPortInventory(BaseModel):
    ports: list[PhysicalPort]
