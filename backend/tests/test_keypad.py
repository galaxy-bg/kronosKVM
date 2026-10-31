from backend.app.hardware.keypad import KeyScanner, MainMenu, Menu


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


def test_lcd_client_uses_dedicated_identity_for_read_and_confirmed_action(tmp_path, monkeypatch):
    import io

    from backend.app.hardware import keypad

    token = tmp_path / "lcd-token"
    token.write_text("a" * 64)
    requests = []

    def open_request(request, timeout):
        requests.append(request)
        return io.StringIO('{"ok":true}')

    monkeypatch.setattr(keypad, "urlopen", open_request)
    client = keypad.RemoteAssistClient(token_path=token)
    client.get("/system/network")
    client.action("enable")
    assert requests[0].get_method() == "GET"
    assert requests[1].get_method() == "POST"
    assert requests[1].full_url.endswith("/remote-assist/enable")
    assert all(request.get_header("X-kdx-lcd-token") == "a" * 64 for request in requests)


class LCDClient:
    def __init__(self):
        self.data = {"ready": True, "ethernet_ip": "192.168.31.26", "ap_enabled": True,
                     "vpn": {"enabled": False, "state": "off"},
                     "access": {"enabled": False, "state": "off"}}
        self.actions = []

    def snapshot(self):
        return self.data.copy()

    def control(self, action):
        self.actions.append(action)
        return "request-1"


def open_section(menu, section):
    menu.section, menu.selected, menu.page = section, 0, None
    menu.refresh()


def test_lcd_starts_on_status_and_menu_has_only_mvp_sections():
    menu = MainMenu(LCDClient())
    menu.refresh()
    assert menu.view()["title"] == "Status"
    assert menu.view()["rows"][:2] == ["System Ready", "ETH: 192.168.31.26"]
    menu.press("ok")
    assert menu.view()["items"] == ["Status", "Network", "Remote Assist", "System"]
    menu.press("up")
    menu.press("ok")
    assert menu.section == "System"
    assert "Console" not in str(menu.view())


def test_lcd_confirmation_defaults_cancel_and_expires():
    now = [0]
    client = LCDClient()
    menu = MainMenu(client, clock=lambda: now[0])
    open_section(menu, "System")
    menu.selected = 3
    menu.press("ok")
    assert menu.view()["selected"] == 0
    menu.press("ok")
    assert not client.actions
    menu.press("ok")
    menu.press("down")
    now[0] = 16
    menu.press("ok")
    assert not client.actions
    assert menu.confirm_selected == 0


def test_every_lcd_action_is_confirmed_and_submitted_once():
    for section, index, action in [("Network", 0, "diagnostics"),
                                   ("Network", 1, "ap-off"),
                                   ("Network", 2, "access-on"),
                                   ("Remote Assist", 1, "connect"),
                                   ("System", 2, "reboot"), ("System", 3, "poweroff")]:
        client = LCDClient()
        menu = MainMenu(client)
        open_section(menu, section)
        menu.selected = index
        menu.press("ok")
        assert not client.actions
        menu.press("down")
        menu.press("ok")
        for _ in range(4):
            menu.press("ok")
        assert client.actions == [action]
        assert menu.pending
        client.data["result"] = {"request_id": "other", "ok": True}
        menu.refresh()
        assert menu.pending
        client.data["result"] = {"request_id": "request-1", "ok": False,
                                 "message": "Host action failed"}
        menu.refresh()
        assert menu.pending is None
        assert menu.view()["rows"] == ["Host action failed"]


def test_lcd_toggles_use_actual_state():
    client = LCDClient()
    client.data.update(ap_enabled=False, vpn={"enabled": True}, access={"enabled": True})
    menu = MainMenu(client)
    open_section(menu, "Network")
    assert [o[1] for o in menu.options()] == ["diagnostics", "ap-on", "access-off"]
    open_section(menu, "Remote Assist")
    assert menu.options()[1] == ("Disconnect", "disconnect")


def test_lcd_information_scroll_back_and_idle_return():
    now = [0]
    client = LCDClient()
    client.data["services"] = [f"service {i}: active" for i in range(10)]
    menu = MainMenu(client, clock=lambda: now[0])
    open_section(menu, "System")
    menu.selected = 1
    menu.press("ok")
    for _ in range(20):
        menu.press("down")
    assert menu.offset == 6
    menu.press("back")
    assert menu.page is None
    assert menu.section is None
    menu.press("back")
    assert menu.section is None
    now[0] = 31
    menu.refresh()
    assert menu.section == "Status"
    assert not client.actions


def test_idle_never_hides_pending_action_and_status_errors_are_explicit():
    now = [0]
    client = LCDClient()
    client.data["errors"] = ["API unavailable"]
    menu = MainMenu(client, clock=lambda: now[0])
    menu.refresh()
    assert menu.rows()[0] == "Error: API unavailable"
    menu.pending = "request-1"
    menu.section = "System"
    now[0] = 31
    menu.refresh()
    assert menu.section == "System"


def test_physical_ok_enters_every_submenu_and_back_stays_at_top_level():
    for index, name in enumerate(("Status", "Network", "Remote Assist", "System")):
        menu = MainMenu(LCDClient())
        scanner = KeyScanner()
        now = [0.0]

        def release_key(key, now=now, scanner=scanner, menu=menu):
            now[0] += 1
            scanner.update([], now[0])
            scanner.update([], now[0] + 0.1)
            scanner.update([key], now[0] + 0.2)
            scanner.update([key], now[0] + 0.3)
            scanner.update([], now[0] + 0.4)
            event = scanner.update([], now[0] + 0.5)
            assert event == key
            menu.press(event)

        release_key("ok")
        for _ in range(index):
            release_key("down")
        assert menu.view()["selected"] == index
        release_key("ok")
        assert menu.view()["title"] == name
        if name != "Status":
            assert "items" in menu.view()
            release_key("back")
            assert menu.section is None
            release_key("back")
            assert menu.section is None


def test_back_from_confirmation_returns_to_root_without_action():
    client = LCDClient()
    menu = MainMenu(client)
    open_section(menu, "System")
    menu.selected = 3
    menu.press("ok")
    menu.press("down")
    menu.press("back")
    assert menu.section is None
    assert menu.confirm is None
    assert menu.selected == 3
    assert client.actions == []
    menu.press("ok")
    assert menu.section == "System"


def test_enclosure_button_mapping_matches_operator_order():
    from backend.app.hardware.keypad import PINS

    assert PINS == {"down": 5, "up": 6, "ok": 19, "back": 13}
