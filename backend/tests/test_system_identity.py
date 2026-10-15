from backend.app.services import system


def test_product_model_and_full_serial_keep_hardware_details(monkeypatch):
    monkeypatch.setattr(system, "_read_text", lambda *args: "Raspberry Pi 4 Model B Rev 1.5")
    monkeypatch.setattr(system, "read_identity", lambda: {"serial": "100000008ed89866"})
    info = system.get_system_info()
    assert info.model == "Galaxy-RP4"
    assert info.serial == "100000008ed89866"
    assert info.hardware_model == "Raspberry Pi 4 Model B Rev 1.5"


def test_missing_identity_does_not_fabricate_a_label_or_break_system_status(monkeypatch):
    monkeypatch.setattr(system, "_read_text", lambda *args: "unknown")

    def unavailable():
        raise ValueError("Serial unavailable")

    monkeypatch.setattr(system, "read_identity", unavailable)
    info = system.get_system_info()
    assert info.serial is None
    assert info.model == "unknown"
