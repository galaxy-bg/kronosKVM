from backend.app.hardware.keypad import SECTIONS, KeyScanner, MainMenu, Menu


class Client:
    def __init__(self):
        self.data = {
            "installed": True, "stale": False, "pending": False,
            "profile": {"name": "Office"}, "state": "off",
        }
        self.actions = []

    def status(self):
        return self.data.copy()

    def action(self, action):
        self.actions.append(action)
        return {"request_id": "test-request"}

    def get(self, path):
        return {"hostname": "test", "uptime_seconds": 120, "load_average": [0.1],
                "model": "Pi"}


def test_enable_requires_confirmation_and_host_result():
    client = Client()
    menu = Menu(client)
    menu.press("ok")
    menu.press("ok")
    assert client.actions == []
    menu.press("ok")
    assert client.actions == ["enable"]
    assert menu.lines()[1] == "Uygulaniyor..."
    menu.press("ok")
    assert client.actions == ["enable"]
    client.data["last_result"] = {"request_id": "other", "ok": True}
    menu.refresh()
    assert menu.pending
    client.data["last_result"] = {"request_id": "test-request", "ok": False}
    menu.refresh()
    assert menu.lines()[1] == "Islem basarisiz"


def test_back_and_expiry_cancel_confirmation():
    now = [0]
    client = Client()
    menu = Menu(client, clock=lambda: now[0])
    menu.press("ok")
    menu.press("ok")
    menu.press("back")
    assert menu.confirm is None
    menu.press("ok")
    menu.press("ok")
    now[0] = 11
    menu.press("ok")
    assert client.actions == []


def test_stale_pending_and_missing_profile_block_enable():
    for field, value in [("stale", True), ("pending", True), ("profile", None)]:
        client = Client()
        client.data[field] = value
        menu = Menu(client)
        for _ in range(4):
            menu.press("ok")
        assert client.actions == []


def test_disable_and_startup_actions_are_explicit():
    for index, action in enumerate(["enable", "disable", "boot-on", "boot-off"]):
        client = Client()
        menu = Menu(client)
        menu.press("ok")
        for _ in range(index):
            menu.press("down")
        menu.press("ok")
        menu.press("ok")
        assert client.actions == [action]


def test_unavailable_status_clears_confirmation():
    client = Client()
    menu = Menu(client)
    menu.press("ok")
    menu.press("ok")
    client.data = {}
    menu.press("ok")
    assert menu.confirm is None
    assert client.actions == []


def test_timeout_does_not_claim_success():
    now = [0]
    menu = Menu(Client(), clock=lambda: now[0])
    for _ in range(3):
        menu.press("ok")
    now[0] = 91
    menu.refresh()
    assert menu.lines()[1] == "Sonuc belirsiz"


def test_held_key_emits_once_on_release():
    scanner = KeyScanner()
    scanner.update([], 0)
    scanner.update([], 0.1)
    scanner.update(["ok"], 1)
    assert scanner.update(["ok"], 2) is None
    assert scanner.update(["ok"], 20) is None
    scanner.update([], 21)
    assert scanner.update([], 21.1) == "ok"
    assert scanner.update([], 22) is None


def test_startup_hold_chord_and_bounce_do_not_trigger():
    scanner = KeyScanner()
    scanner.update(["ok"], 0)
    scanner.update(["ok"], 1)
    scanner.update([], 2)
    assert scanner.update([], 2.1) is None
    scanner.update(["ok"], 3)
    scanner.update(["ok"], 3.1)
    scanner.update(["ok", "back"], 4)
    scanner.update(["ok", "back"], 4.1)
    scanner.update(["ok"], 5)
    scanner.update(["ok"], 5.1)
    scanner.update([], 6)
    assert scanner.update([], 6.1) is None
    scanner.update(["ok"], 7)
    scanner.update([], 7.01)
    assert scanner.update([], 7.2) is None


def test_main_menu_navigation_and_back_preserve_selection():
    menu = MainMenu(Client())
    assert menu.view()["items"] == list(SECTIONS)
    assert menu.view()["selected"] == 0
    menu.press("up")
    assert menu.view()["selected"] == len(SECTIONS) - 1
    menu.press("down")
    menu.press("ok")
    assert menu.view()["title"] == "Dashboard"
    assert "Uptime: 0h 2m" in menu.view()["rows"]
    menu.press("back")
    assert menu.section is None
    assert menu.selected == 0


def test_remote_controls_require_confirmation_inside_section():
    client = Client()
    menu = MainMenu(client)
    for _ in range(SECTIONS.index("Remote Assist")):
        menu.press("down")
    menu.press("ok")
    assert menu.view()["selected"] == 0
    assert client.actions == []
    menu.press("ok")
    assert menu.view()["title"] == "Onay"
    menu.press("back")
    assert menu.section == "Remote Assist"
    assert menu.remote.confirm is None
    menu.press("ok")
    menu.press("ok")
    assert client.actions == ["enable"]
    menu.press("back")
    assert menu.section is None
    menu.press("ok")
    assert menu.view()["rows"][0] == "Uygulaniyor..."
    assert client.actions == ["enable"]


def test_section_error_and_scroll_are_bounded():
    menu = MainMenu(Client())
    menu.selected = SECTIONS.index("Services")
    menu.press("ok")
    assert menu.view()["rows"][0] == "Durum alinamiyor"
    menu.details = [str(index) for index in range(10)]
    for _ in range(20):
        menu.press("down")
    assert menu.offset == 6
    for _ in range(20):
        menu.press("up")
    assert menu.offset == 0
