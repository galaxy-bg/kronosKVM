"""Renderer for the appliance's installed 160x128 Waveshare-compatible SPI LCD."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path


class LCDPanel:
    def __init__(self, driver_path="/opt/infrabox-lcd", lcd=None, font_path=None, logo_path=None):
        from PIL import Image, ImageDraw, ImageFont

        self.image = Image
        self.draw = ImageDraw
        font_path = font_path or "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        self.font = ImageFont.truetype(font_path, 11)
        self.small = ImageFont.truetype(font_path, 9)
        self.brand = ImageFont.truetype(font_path, 15)
        self.lcd = lcd
        backlight = os.environ.get("KRONOSKVM_LCD_BL_PIN")
        self.backlight_pin = int(backlight) if backlight is not None else None
        if self.lcd is None:
            sys.path.insert(0, driver_path)
            from lib.LCD_1inch8 import LCD_1inch8

            self.lcd = LCD_1inch8(spi_freq=4000000, rst=27, dc=25, bl=self.backlight_pin)
            if self.backlight_pin is not None:
                self.lcd.bl_DutyCycle(0)
            self.lcd.Init()
        self.ip = "LAN yok"
        self.next_network = 0
        logo_path = logo_path or (
            Path(__file__).resolve().parents[3] / "frontend/src/infrabox-logo-transparent.png"
        )
        try:
            with Image.open(logo_path) as source:
                self.logo = source.convert("RGBA")
            self.logo.thumbnail((62, 65), Image.Resampling.LANCZOS)
        except OSError:
            self.logo = None

    def splash(self):
        canvas = self.image.new("RGB", (160, 128), "#101b24")
        draw = self.draw.Draw(canvas)
        if self.logo:
            canvas.paste(self.logo, ((160 - self.logo.width) // 2, 5), self.logo)
        draw.text((80, 74), "KDX InfraBox", font=self.brand, fill="white", anchor="mt")
        draw.text((80, 96), "Booting...", font=self.font, fill="#53dca5", anchor="mt")
        draw.rounded_rectangle((46, 115, 114, 118), radius=1, fill="#087f5b")
        self.lcd.ShowImage(canvas)
        if self.backlight_pin is not None:
            # Init clears the panel; expose it only after the complete logo frame.
            self.lcd.bl_DutyCycle(100)
        return canvas

    def fit(self, draw, text, width, font=None):
        font = font or self.font
        text = str(text).replace("\n", " ")
        if draw.textlength(text, font=font) <= width:
            return text
        while text and draw.textlength(text + "…", font=font) > width:
            text = text[:-1]
        return text + "…"

    def show(self, menu):
        # Feedback is display-only. Power actions belong to the dedicated GPIO service.
        try:
            status = json.loads(Path("/run/kronoskvm-power-button/status.json").read_text())
            age = time.time() - float(status["updated_at"])
            if status.get("pressed") is True and 0 <= age <= 2:
                return self.show_power_button(status)
        except (OSError, ValueError, KeyError, TypeError):
            pass
        if time.monotonic() >= self.next_network:
            self.next_network = time.monotonic() + 10
            try:
                links = json.loads(subprocess.check_output(
                    ["ip", "-j", "-4", "addr", "show", "eth0"], timeout=1,
                ))
                self.ip = next(
                    addr["local"] for link in links for addr in link["addr_info"]
                    if addr["scope"] == "global"
                )
            except (OSError, ValueError, StopIteration, subprocess.SubprocessError):
                self.ip = "LAN yok"
        canvas = self.image.new("RGB", (160, 128), "#101b24")
        draw = self.draw.Draw(canvas)
        view = menu.view()
        draw.rectangle((0, 0, 159, 20), fill="#087f5b")
        title = "InfraBox / Menu" if menu.section is None else view["title"]
        draw.text((5, 2), self.fit(draw, title, 150), font=self.font, fill="white")
        status = menu.remote.status
        if not status.get("installed") or status.get("stale", True):
            subtitle = "API: Bilgi alinamiyor"
        elif menu.section == "Remote Assist":
            states = {"off": "OFF", "connected": "Bagli", "waiting_handshake": "Bekliyor",
                      "disconnected": "Bagli degil", "setup_required": "Profil yok",
                      "stop_failed": "Hata"}
            vpn = states.get(status.get("state"), "?")
            subtitle = vpn + " / Boot:" + ("ON" if status.get("autostart") else "OFF")
        else:
            subtitle = self.ip
        draw.text((5, 23), self.fit(draw, subtitle, 150, self.small),
                  font=self.small, fill="#a5c5ba")
        selected = view.get("selected")
        rows = view.get("items", view.get("rows", []))
        start = max(0, min(selected - 1, len(rows) - 4)) if selected is not None else view.get(
            "offset", 0,
        )
        for index, text in enumerate(rows[start:start + 4], start=start):
            y = 38 + (index - start) * 17
            highlighted = index == selected
            if highlighted:
                draw.rounded_rectangle((3, y - 1, 151, y + 15), radius=3, fill="#087f5b")
                draw.polygon([(7, y + 4), (7, y + 10), (11, y + 7)], fill="white")
            draw.text((15 if selected is not None else 5, y),
                      self.fit(draw, text, 132 if selected is not None else 145),
                      font=self.font, fill="white" if highlighted else "#d6e1dc")
        if len(rows) > 4:
            draw.line((156, 38, 156, 103), fill="#2f4940", width=2)
            thumb = max(8, int(66 * 4 / len(rows)))
            top = 38 + int((66 - thumb) * start / (len(rows) - 4))
            draw.line((156, top, 156, top + thumb - 1), fill="#53dca5", width=2)
        draw.line((4, 109, 155, 109), fill="#2f4940")
        footer = "OK: Sec  " + str(selected + 1) + "/" + str(len(rows)) if selected is not None \
            else "OK: Yenile"
        if menu.remote.confirm and menu.section == "Remote Assist":
            footer = "OK: Onayla"
        if menu.section is not None:
            footer += "  BACK: Geri"
        draw.text((5, 114), self.fit(draw, footer, 150, self.small),
                  font=self.small, fill="#a5c5ba")
        self.lcd.ShowImage(canvas)
        return canvas

    def show_power_button(self, status):
        canvas = self.image.new("RGB", (160, 128), "#101b24")
        draw = self.draw.Draw(canvas)
        action = status.get("action")
        title = {"reboot": "Restart", "poweroff": "Power off"}.get(action, "Power button")
        draw.text((80, 12), title, font=self.brand, fill="white", anchor="mt")
        draw.text((80, 40), "Birak: yeniden baslat" if action == "reboot" else
                  "Birak: guvenli kapat" if action == "poweroff" else "Basili tut...",
                  font=self.small, fill="#53dca5", anchor="mt")
        duration = max(0, float(status.get("held_seconds", 0)))
        draw.text((80, 64), f"{duration:.1f} s", font=self.brand, fill="white", anchor="mt")
        draw.rectangle((10, 90, 150, 96), fill="#2f4940")
        draw.rectangle((10, 90, 10 + int(140 * min(duration / 5, 1)), 96), fill="#087f5b")
        draw.text((80, 106), "2s: Restart / 5s: Kapat", font=self.small,
                  fill="#a5c5ba", anchor="mt")
        self.lcd.ShowImage(canvas)
        return canvas
