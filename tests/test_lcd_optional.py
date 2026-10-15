"""Headless startup must not import or initialize optional GPIO dependencies."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "keypad_panel_runner", Path(__file__).parents[1] / "scripts/keypad-panel.py"
)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_lcd_requirements():
    for missing in (
        "/etc/kronoskvm/lcd.enabled",
        "/opt/infrabox-lcd/lib/LCD_1inch8.py",
        "/dev/spidev0.0",
        None,
    ):
        def present(path, missing=missing):
            return str(path) != missing
        with patch.object(Path, "is_file", present), patch.object(Path, "exists", present):
            assert runner.lcd_available() is (missing is None)


def test_headless_exit_before_gpio_import(capsys):
    with patch.object(runner, "lcd_available", return_value=False), \
         patch("sys.argv", ["keypad-panel.py", "--lcd"]), \
         patch.dict("sys.modules", {"gpiozero": None, "lcd_panel": None}):
        runner.main()
    assert "skipping LCD and keypad" in capsys.readouterr().out
