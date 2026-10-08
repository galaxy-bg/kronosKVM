#!/usr/bin/env python3
"""Provision persistent AP security; API requests contain no host commands or paths."""

import argparse
import configparser
import fcntl
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.services.device_identity import read_identity  # noqa: E402
from backend.app.services.wifi_config import (  # noqa: E402
    default_password,
    network_psk,
    validate_password,
    validate_wifi_update,
)

STATE = Path("/var/lib/kronoskvm/state")
CONFIG = Path("/etc/kronoskvm/wifi-ap.json")
PROFILES = Path("/etc/NetworkManager/system-connections")
LEGACY = Path("/etc/hostapd/hostapd.conf")


def run(args, required=True):
    result = subprocess.run(args, capture_output=True, text=True, timeout=40)
    if required and result.returncode:
        raise RuntimeError("Wi-Fi host operation failed")
    return result


def atomic(path, text, public=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".wifi-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(text)
            os.fchmod(stream.fileno(), 0o640 if public else 0o600)
            if public:
                os.fchown(stream.fileno(), 10001, 20)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def profile():
    helper = Path(__file__).with_name("management-ap.sh")
    result = run(["bash", "-c", 'source "$1"; management_ap_uuid', "wifi", str(helper)], False)
    uuid = result.stdout.strip() if not result.returncode else ""
    if uuid:
        for path in PROFILES.glob("*.nmconnection"):
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            parser.read(path)
            if parser.get("connection", "uuid", fallback="") == uuid:
                if (parser.get("wifi", "mode", fallback="") != "ap"
                        or parser.get("connection", "interface-name", fallback="") != "wlan0"):
                    raise RuntimeError("Wi-Fi AP profile is invalid")
                return path, parser, uuid
        raise RuntimeError("Wi-Fi AP profile must have a persistent NetworkManager keyfile")
    if LEGACY.exists() and "interface=wlan0" in LEGACY.read_text().splitlines():
        return LEGACY, None, None
    raise RuntimeError("Wi-Fi AP profile is unavailable")


def legacy_values(text):
    return dict(line.split("=", 1) for line in text.splitlines()
                if "=" in line and not line.lstrip().startswith("#"))


def settings(path, parser):
    if parser is not None:
        return (parser.get("wifi", "ssid"),
                parser.get("wifi-security", "key-mgmt", fallback="") == "wpa-psk",
                parser.get("wifi-security", "psk", fallback=""))
    value = legacy_values(path.read_text())
    return value["ssid"], value.get("wpa") == "2", value.get(
        "wpa_passphrase", value.get("wpa_psk", ""))


def select_config(identity, ssid, secured, existing, password=None):
    factory = default_password(identity["serial"])
    if password is not None:
        return {"serial": identity["serial"], "password": validate_password(password),
                "default": password == factory}
    if CONFIG.exists():
        value = json.loads(CONFIG.read_text())
        if value.get("default"):
            return {"serial": identity["serial"], "password": factory, "default": True}
        if "password" in value:
            validate_password(value["password"])
        elif not re.fullmatch(r"[0-9a-fA-F]{64}", value.get("raw_psk", "")):
            raise RuntimeError("Saved Wi-Fi configuration is invalid")
        return value
    # Adopt pre-existing protected installations rather than resetting their password.
    if secured:
        if re.fullmatch(r"[0-9a-fA-F]{64}", existing):
            return {"serial": identity["serial"], "raw_psk": existing.lower(), "default": False}
        return {"serial": identity["serial"], "password": validate_password(existing),
                "default": existing == factory}
    return {"serial": identity["serial"], "password": factory, "default": True}


def radio_info():
    try:
        text = run(["iw", "dev", "wlan0", "info"], False).stdout
    except OSError:
        return {}
    match = re.search(r"channel (\d+) \((\d+) MHz\), width: (\d+) MHz", text)
    if not match or "type AP" not in text:
        return {}
    return dict(zip(("channel", "frequency_mhz", "width_mhz"), map(int, match.groups())))


def performance_available():
    try:
        text = run(["iw", "dev", "wlan0", "info"], False).stdout
        phy = re.search(r"wiphy (\d+)", text)
        if not phy:
            return False
        capabilities = run(["iw", "phy", f"phy{phy[1]}", "info"], False).stdout
        line = next((line for line in capabilities.splitlines()
                     if "5180" in line and "[36]" in line), "")
        return bool(line) and not any(flag in line.lower() for flag in (
            "disabled", "no ir", "radar detection",
        ))
    except OSError:
        return False


def verify_radio(mode):
    frequency = radio_info().get("frequency_mhz", 0)
    if not (5000 <= frequency < 5900 if mode == "performance" else 2400 <= frequency < 2500):
        raise RuntimeError("Wi-Fi AP did not start on the selected band")


def render_profile(before, parser, psk, mode, width_supported):
    performance = mode == "performance"
    if parser is not None:
        if not parser.has_section("wifi-security"):
            parser.add_section("wifi-security")
        security = {"key-mgmt": "wpa-psk", "proto": "rsn;", "pairwise": "ccmp;",
                    "group": "ccmp;", "psk": psk, "psk-flags": "0"}
        radio = {"band": "a" if performance else "bg", "channel": "36" if performance else "6"}
        if width_supported:
            radio["channel-width"] = "80" if performance else "20"
        changed = any(parser["wifi-security"].get(key) != item for key, item in security.items())
        changed = any(parser["wifi"].get(key) != item for key, item in radio.items()) or changed
        parser["wifi-security"].update(security)
        parser["wifi"].update(radio)
        output = io.StringIO()
        parser.write(output, space_around_delimiters=False)
        return output.getvalue(), changed
    desired = {"wpa": "2", "wpa_key_mgmt": "WPA-PSK", "rsn_pairwise": "CCMP",
               "wpa_psk": psk, "auth_algs": "1", "hw_mode": "a" if performance else "g",
               "channel": "36" if performance else "6", "ieee80211n": "1",
               "ieee80211ac": "1" if performance else "0"}
    if performance:
        desired.update(ht_capab="[HT40+]", vht_oper_chwidth="1", vht_oper_centr_freq_seg0_idx="42")
    owned = {*desired, "wpa_passphrase", "ht_capab", "vht_oper_chwidth",
             "vht_oper_centr_freq_seg0_idx"}
    current = legacy_values(before)
    lines = [line for line in before.splitlines() if line.split("=", 1)[0] not in owned]
    after = "\n".join(lines + [f"{key}={item}" for key, item in desired.items()]) + "\n"
    changed = any(current.get(key) != item for key, item in desired.items())
    changed = any(key in current for key in owned - {*desired, "wpa_passphrase"}) or changed
    return after, changed


def apply(password=None, mode=None):
    identity = read_identity()
    path, parser, uuid = profile()
    ssid, secured, existing = settings(path, parser)
    before = path.read_text()
    previous_config = CONFIG.read_text() if CONFIG.exists() else None
    saved = json.loads(previous_config) if previous_config else {}
    selected = validate_wifi_update({"mode": mode or saved.get("mode", "standard")})["mode"]
    value = select_config(identity, ssid, secured, existing, password)
    value["mode"] = selected
    value.pop("notice", None)
    psk = (network_psk(value["password"], ssid) if "password" in value else value["raw_psk"])
    width_supported = bool(uuid) and run([
        "nmcli", "-g", "802-11-wireless.channel-width", "connection", "show", "uuid", uuid,
    ], False).returncode == 0

    def activate(selected_mode):
        after, changed = render_profile(before, parser, psk, selected_mode, width_supported)
        frequency = radio_info().get("frequency_mhz", 0)
        active_band = (5000 <= frequency < 5900 if selected_mode == "performance"
                       else 2400 <= frequency < 2500)
        if changed:
            atomic(path, after)
            if uuid:
                run(["nmcli", "connection", "load", str(path)])
        # At boot, an unchanged saved profile may not have activated yet.
        if changed or not active_band:
            if uuid:
                run(["nmcli", "--wait", "25", "connection", "up", "uuid", uuid])
            else:
                run(["systemctl", "restart", "hostapd.service"])
        verify_radio(selected_mode)

    try:
        try:
            if selected == "performance" and not performance_available():
                raise RuntimeError("5 GHz channel is unavailable")
            activate(selected)
        except (RuntimeError, subprocess.TimeoutExpired):
            if selected != "performance":
                raise
            # Save the working fallback so failed 5 GHz does not repeat at every boot.
            activate("standard")
            value["mode"] = "standard"
            value["notice"] = "5 GHz could not start. AP returned to Standard (2.4 GHz)."
        atomic(CONFIG, json.dumps(value) + "\n")
    except Exception:
        atomic(path, before)
        if previous_config is None:
            CONFIG.unlink(missing_ok=True)
        else:
            atomic(CONFIG, previous_config)
        if uuid:
            run(["nmcli", "connection", "load", str(path)], False)
            run(["nmcli", "--wait", "25", "connection", "up", "uuid", uuid], False)
        else:
            run(["systemctl", "restart", "hostapd.service"], False)
        raise RuntimeError("Wi-Fi update failed; previous configuration restored") from None


def publish(error="", request_id=None):
    status = {"installed": False, "state": "unavailable", "updated_at": time.time()}
    try:
        path, parser, _ = profile()
        ssid, secured, _ = settings(path, parser)
        config = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
        status.update(installed=True, ssid=ssid, secured=secured,
                      default_password=bool(config.get("default")),
                      state="secured" if secured else "open", mode=config.get("mode", "standard"),
                      performance_available=performance_available(), **radio_info())
        if config.get("notice"):
            status["notice"] = config["notice"]
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        error = error or "Wi-Fi configuration is unavailable"
    try:
        previous = json.loads((STATE / "wifi-status.json").read_text())
    except (OSError, ValueError):
        previous = {}
    if request_id or previous.get("request_id"):
        status["request_id"] = request_id or previous["request_id"]
    # Keep an action error until the next successful action; periodic refresh must not hide it.
    if not error:
        try:
            error = json.loads((STATE / "wifi-status.json").read_text()).get("error", "")
        except (OSError, ValueError):
            pass
    if error:
        status["error"] = error
    atomic(STATE / "wifi-status.json", json.dumps(status) + "\n", public=True)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    group = cli.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true")
    group.add_argument("--request", action="store_true")
    args = cli.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("Run as root")
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / "wifi.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        error = ""
        request_id = None
        try:
            if args.request:
                target = STATE / "wifi-request.json"
                try:
                    # Consume once, including malformed requests; never log their contents.
                    if target.stat().st_size > 1024:
                        raise ValueError()
                    value = json.loads(target.read_text())
                    if not isinstance(value, dict):
                        raise ValueError()
                    if (not isinstance(value.get("request_id"), str)
                            or not re.fullmatch(r"[0-9a-f]{32}", value["request_id"])):
                        raise ValueError()
                    request_id = value["request_id"]
                    change = validate_wifi_update(
                        {key: item for key, item in value.items() if key != "request_id"},
                    )
                finally:
                    target.unlink(missing_ok=True)
                apply(**change)
            elif args.apply:
                apply()
            if args.request or args.apply:
                (STATE / "wifi-status.json").unlink(missing_ok=True)
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
            error = "Wi-Fi update failed; check the AP configuration and try again"
        publish(error, request_id)
        if error and (args.apply or args.request):
            raise SystemExit(error)


if __name__ == "__main__":
    main()
