from abc import ABC, abstractmethod

from backend.app.models import Capability


class HardwareModule(ABC):
    @abstractmethod
    def capability(self) -> Capability:
        """Return a non-fatal snapshot of the module state."""
