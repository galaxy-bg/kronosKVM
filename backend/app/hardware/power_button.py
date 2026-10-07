"""Release-based power gestures; no GPIO or system actions in this module."""


class PowerButton:
    def __init__(self, debounce=0.05):
        self.debounce = debounce
        self.candidate = None
        self.changed_at = 0
        self.stable = None
        self.armed = False
        self.started = None

    @staticmethod
    def action(duration):
        if duration >= 5:
            return "poweroff"
        if duration >= 2:
            return "reboot"
        return None

    def update(self, pressed, now):
        if pressed != self.candidate:
            self.candidate, self.changed_at = pressed, now
        if now - self.changed_at < self.debounce or pressed == self.stable:
            return None
        self.stable = pressed
        if pressed:
            if self.armed:
                self.started = self.changed_at
            return None
        result = None
        if self.started is not None:
            result = self.action(self.changed_at - self.started)
        self.started = None
        self.armed = True
        return result

    def feedback(self, now):
        duration = max(0, now - self.started) if self.started is not None else 0
        action = self.action(duration)
        messages = {
            None: "Keep holding...",
            "reboot": "Release to restart",
            "poweroff": "Release to shut down",
        }
        return {
            "pressed": self.started is not None,
            "held_seconds": round(duration, 1),
            "action": action,
            "message": messages[action],
        }
