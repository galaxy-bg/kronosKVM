#!/usr/bin/env python3
"""GPIO keypad runner. Publishes LCD lines; --test-buttons never calls the API."""

import argparse
import json
import sys
import time
from contextlib import ExitStack
from pathlib import Path

# Run on the host without importing the API package's pydantic dependencies.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend/app/hardware"))
from keypad import PINS, KeyScanner, MainMenu, RemoteAssistClient  # noqa: E402


def lcd_available():
    """SPI has no reliable panel-presence detection; require explicit provisioning."""
    return (
        Path("/etc/kronoskvm/lcd.enabled").is_file()
        and Path("/opt/infrabox-lcd/lib/LCD_1inch8.py").is_file()
        and Path("/dev/spidev0.0").exists()
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-buttons", action="store_true")
    parser.add_argument("--lcd", action="store_true", help="Use the installed 160x128 SPI LCD")
    parser.add_argument("--output", type=Path, help="Atomic JSON output for the LCD renderer")
    args = parser.parse_args()
    if args.lcd and not args.test_buttons and not lcd_available():
        print("LCD disabled or unavailable; skipping LCD and keypad", flush=True)
        return
    from gpiozero import Button

    buttons = {}
    scanner = KeyScanner()
    next_refresh = 0
    menu = MainMenu(RemoteAssistClient())
    panel = None
    if args.lcd and not args.test_buttons:
        from lcd_panel import LCDPanel

        panel = LCDPanel()
        panel.splash()
        time.sleep(2)
    previous = None
    with ExitStack() as stack:
        for key, pin in PINS.items():
            button = stack.enter_context(Button(pin, pull_up=True, bounce_time=0.08))
            buttons[key] = button
        while True:
            time.sleep(0.02)
            now = time.monotonic()
            active = frozenset(key for key, button in buttons.items() if button.is_pressed)
            key = scanner.update(active, now)
            if args.test_buttons:
                if key:
                    print(f"{key}: BCM{PINS[key]}", flush=True)
                continue
            if key:
                menu.press(key)
            elif now >= next_refresh:
                menu.refresh()
            else:
                continue
            next_refresh = now + 1
            lines = menu.lines()
            if panel:
                panel.show(menu)
            if args.output:
                temporary = args.output.with_suffix(".tmp")
                temporary.write_text(json.dumps({
                    "lines": lines, "view": menu.view(), "updated_at": time.time(),
                }))
                temporary.replace(args.output)
            if lines != previous:
                print(" | ".join(lines), flush=True)
                previous = lines


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
