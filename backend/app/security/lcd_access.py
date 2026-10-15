"""Optional local LCD identity with a fixed, narrow API allowlist."""

import hmac
import os
from pathlib import Path

READ_PATHS = {
    "/api/v1/system/info", "/api/v1/system/network", "/api/v1/connections",
    "/api/v1/storage", "/api/v1/recovery", "/api/v1/tasks", "/api/v1/services",
    "/api/v1/logs", "/api/v1/remote-assist",
}
ACTION_PATHS = {
    "/api/v1/remote-assist/" + action
    for action in ("enable", "disable", "boot-on", "boot-off")
}


def lcd_authenticated(scope, headers):
    if scope["type"] != "http" or (scope.get("client") or (None,))[0] not in {
        "127.0.0.1", "::1",
    }:
        return False
    # Reverse-proxied browser requests must never use the local identity.
    if headers.get("x-forwarded-for") or headers.get("x-real-ip"):
        return False
    method, path = scope.get("method"), scope["path"]
    if not ((method == "GET" and path in READ_PATHS)
            or (method == "POST" and path in ACTION_PATHS)):
        return False
    supplied = headers.get("x-kdx-lcd-token", "")
    if len(supplied) != 64 or any(char not in "0123456789abcdef" for char in supplied):
        return False
    try:
        expected = Path(os.environ.get(
            "KRONOSKVM_LCD_TOKEN_PATH", "/etc/kronoskvm/lcd-api-token",
        )).read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return False
    return len(expected) == 64 and hmac.compare_digest(supplied, expected)
