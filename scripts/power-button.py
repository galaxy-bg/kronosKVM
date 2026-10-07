#!/usr/bin/env python3
"""Dedicated GPIO button. Do not attach to Witty Pi's MCU-controlled switch."""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend/app/hardware"))
from power_button import PowerButton  # noqa: E402

STATUS = Path("/run/kronoskvm-power-button/status.json")
# Reserved by SPI/I2C, panel, keypad or Witty Pi. Wiring must be confirmed first.
RESERVED = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 17, 19, 24, 25, 27}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pin", type=int, required=True, help="Confirmed BCM GPIO, not physical pin"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report gestures without power actions"
    )
    args = parser.parse_args()
    if not 0 <= args.pin <= 27 or args.pin in RESERVED:
        parser.error("Pin is reserved or outside the Pi 4 GPIO header range")
    if not args.dry_run and os.geteuid() != 0:
        parser.error("Power actions require root")
    from gpiozero import Button

    running = True

    def stop(signum, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    controller = PowerButton()
    STATUS.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    next_status = 0
    try:
        with Button(args.pin, pull_up=True, bounce_time=None) as button:
            while running:
                now = time.monotonic()
                action = controller.update(button.is_pressed, now)
                if now >= next_status:
                    status = controller.feedback(now)
                    status["updated_at"] = time.time()
                    temporary = STATUS.with_suffix(".tmp")
                    temporary.write_text(json.dumps(status))
                    temporary.chmod(0o644)
                    temporary.replace(STATUS)
                    next_status = now + 0.1
                if action:
                    print(
                        f"Power button: {action}" + (" (dry run)" if args.dry_run else ""),
                        flush=True,
                    )
                    if not args.dry_run:
                        try:
                            subprocess.run(["systemctl", action], check=True)
                        except subprocess.CalledProcessError:
                            print("Power request failed; release and retry", flush=True)
                        else:
                            break
                time.sleep(0.01)
    finally:
        STATUS.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
