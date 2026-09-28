"""Four-button local menu, independent of the LCD driver."""

import json
import time
from urllib.request import Request, urlopen

PINS = {"up": 5, "down": 6, "ok": 13, "back": 19}
ITEMS = (
    ("Destegi ac", "enable"),
    ("Destegi kapat", "disable"),
    ("Acilista ac", "boot-on"),
    ("Acilista kapat", "boot-off"),
)


class KeyScanner:
    """Debounced release events; startup holds and multi-key chords are ignored."""

    def __init__(self):
        self.armed = False
        self.candidate = None
        self.chord = False
        self.last_active = None
        self.changed_at = 0

    def update(self, active, now):
        active = frozenset(active)
        if active != self.last_active:
            self.last_active, self.changed_at = active, now
        if now - self.changed_at < 0.08:
            return None
        if not active:
            key = self.candidate if self.armed and not self.chord else None
            self.armed, self.candidate, self.chord = True, None, False
            return key
        if self.armed:
            if len(active) > 1 or (self.candidate and self.candidate not in active):
                self.chord = True
            elif not self.chord:
                self.candidate = next(iter(active))
        return None


class RemoteAssistClient:
    def __init__(self, base_url="http://127.0.0.1:8000"):
        self.base_url = base_url.rstrip("/") + "/api/v1"
        self.url = self.base_url + "/remote-assist"

    def get(self, path):
        with urlopen(self.base_url + path, timeout=2) as response:
            return json.load(response)

    def status(self):
        with urlopen(self.url, timeout=2) as response:
            return json.load(response)

    def action(self, action):
        if action not in {item[1] for item in ITEMS}:
            raise ValueError("Unsupported keypad action")
        request = Request(self.url + "/" + action, data=b"", method="POST")
        with urlopen(request, timeout=2) as response:
            return json.load(response)


class Menu:
    def __init__(self, client, clock=time.monotonic):
        self.client = client
        self.clock = clock
        self.selected = 0
        self.in_menu = False
        self.confirm = None
        self.confirm_until = 0
        self.pending = None
        self.pending_since = 0
        self.status = {}
        self.message = ""

    def refresh(self):
        try:
            self.status = self.client.status()
        except (OSError, ValueError):
            self.status = {}
        if self.confirm and self.clock() >= self.confirm_until:
            self.confirm = None
        if self.pending:
            result = self.status.get("last_result") or {}
            if result.get("request_id") == self.pending:
                self.message = "Tamamlandi" if result.get("ok") else "Islem basarisiz"
                self.pending = None
            elif self.clock() - self.pending_since >= 90:
                self.message = "Sonuc belirsiz"
                self.pending = None

    def ready(self):
        return (
            self.status.get("installed")
            and not self.status.get("stale", True)
            and not self.status.get("pending")
            and not self.pending
        )

    def press(self, key):
        if key not in PINS:
            return
        self.refresh()
        if key == "back":
            self.confirm = None
            self.in_menu = False
            self.message = ""
            return
        if self.pending:
            return
        if key in {"up", "down"}:
            self.in_menu = True
            self.confirm = None
            self.message = ""
            self.selected = (self.selected + (1 if key == "down" else -1)) % len(ITEMS)
            return
        if not self.in_menu:
            self.in_menu = True
            return
        if not self.ready():
            self.confirm = None
            self.message = "Servis hazir degil"
            return
        action = ITEMS[self.selected][1]
        if action == "enable" and not self.status.get("profile"):
            self.confirm = None
            self.message = "Once VPN profili"
            return
        if self.confirm != action:
            self.confirm = action
            self.confirm_until = self.clock() + 10
            self.message = ""
            return
        self.confirm = None
        try:
            result = self.client.action(action)
            self.pending = result["request_id"]
            self.pending_since = self.clock()
            self.message = ""
        except (OSError, ValueError, KeyError):
            # A timed-out HTTP call may have reached the host. Never claim failure/success.
            self.message = "Sonuc belirsiz"

    def lines(self):
        if not self.status.get("installed") or self.status.get("stale", True):
            return ("Remote Assist", "Durum alinamiyor")
        if self.pending or self.status.get("pending"):
            return ("Remote Assist", "Uygulaniyor...")
        if self.message:
            return ("Remote Assist", self.message)
        if self.confirm:
            return (ITEMS[self.selected][0] + "?", "OK:Onay BACK:Iptal")
        if self.in_menu:
            return ("Remote Assist", ITEMS[self.selected][0])
        states = {
            "off": "Kapali", "connected": "VPN bagli",
            "waiting_handshake": "VPN bekleniyor", "disconnected": "VPN bagli degil",
            "setup_required": "Profil gerekli", "stop_failed": "Kapatma hatasi",
        }
        return ("Remote Assist", states.get(self.status.get("state"), "Durum bilinmiyor"))


SECTIONS = (
    "Dashboard", "Sessions", "Storage", "Recovery", "Remote Assist",
    "Tasks", "Services", "Logs", "Settings",
)
SECTION_PATHS = {
    "Dashboard": "/system/info", "Sessions": "/connections", "Storage": "/storage",
    "Recovery": "/recovery", "Tasks": "/tasks", "Services": "/services",
    "Logs": "/logs?limit=8", "Settings": "/system/network",
}


class MainMenu:
    """UI section navigation around the existing confirmed Remote Assist controls."""

    def __init__(self, client):
        self.client = client
        self.remote = Menu(client)
        self.selected = 0
        self.section = None
        self.offset = 0
        self.details = []
        self.next_detail = 0

    def refresh(self):
        self.remote.refresh()
        if self.section in SECTION_PATHS and time.monotonic() >= self.next_detail:
            self.next_detail = time.monotonic() + 5
            try:
                value = self.client.get(SECTION_PATHS[self.section])
                self.details = self.summarize(self.section, value)
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                self.details = ["Durum alinamiyor", "OK: Tekrar dene"]
            self.offset = min(self.offset, max(0, len(self.details) - 4))

    @staticmethod
    def summarize(section, value):
        if section == "Dashboard":
            minutes = int(value["uptime_seconds"]) // 60
            return [value["hostname"], f"Uptime: {minutes // 60}h {minutes % 60}m",
                    f"Load: {value['load_average'][0]:.2f}", value["model"]]
        if section == "Sessions":
            return [f"Kayitli profil: {len(value)}", "Oturum: Web UI"] + [
                str(item.get("name", "Profil")) for item in value[:20]
            ]
        if section == "Storage":
            return [str(value["status"]), f"Dosya: {value['file_count']}",
                    f"Bos: {value['free_bytes'] / 1024**3:.1f} GiB",
                    f"Toplam: {value['total_bytes'] / 1024**3:.1f} GiB"]
        if section == "Recovery":
            return [value["address"], f"Dosya: {len(value['files'])}", "HTTP / TFTP / FTP",
                    "Yonetim: Web UI"]
        if section == "Tasks":
            tasks = value["tasks"][:20]
            return [f"{item['status']}: {item['title']}" for item in tasks] or ["Gorev yok"]
        if section == "Services":
            return [f"{item['state']}: {item['id']}" for item in value["services"]]
        if section == "Logs":
            return [str(item.get("level", "")) + ": "
                    + str(item.get("event") or item.get("message", ""))
                    for item in value["entries"]] or ["Kayit yok"]
        if section == "Settings":
            rows = []
            for item in value["interfaces"]:
                rows.append(item["name"] + ": " + item["state"])
                rows.extend(item["addresses"])
            return rows or ["Ag bilgisi yok"]
        return []

    def press(self, key):
        if key not in PINS:
            return
        if self.section is None:
            if key in {"up", "down"}:
                self.selected = (self.selected + (1 if key == "down" else -1)) % len(SECTIONS)
            elif key == "ok":
                self.section = SECTIONS[self.selected]
                self.offset = 0
                self.next_detail = 0
                self.remote.in_menu = True
                self.remote.message = ""
                self.refresh()
        elif self.section == "Remote Assist":
            if key == "back" and not self.remote.confirm and not self.remote.message:
                self.section = None
            else:
                self.remote.press(key)
                self.remote.in_menu = True
        elif key == "back":
            self.section = None
        elif key in {"up", "down"}:
            self.offset = max(0, min(max(0, len(self.details) - 4),
                                     self.offset + (1 if key == "down" else -1)))
        elif key == "ok":
            self.next_detail = 0
            self.refresh()

    def view(self):
        if self.section is None:
            return {"title": "Ana Menu", "items": list(SECTIONS), "selected": self.selected}
        if self.section == "Remote Assist":
            remote = self.remote
            first, second = remote.lines()
            if remote.confirm:
                return {"title": "Onay", "rows": [first, "OK: Onayla", "BACK: Iptal"]}
            if (remote.pending or remote.status.get("pending") or remote.message
                    or not remote.status.get("installed") or remote.status.get("stale", True)):
                return {"title": first, "rows": [second, "BACK: Geri"]}
            return {"title": "Remote Assist", "items": [item[0] for item in ITEMS],
                    "selected": remote.selected}
        return {"title": self.section, "rows": self.details, "offset": self.offset}

    def lines(self):
        view = self.view()
        rows = view.get("items", view.get("rows", []))
        index = view.get("selected", view.get("offset", 0))
        return (view["title"], rows[index] if rows else "Bilgi yok")
