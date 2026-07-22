import json
from pathlib import Path

import yaml


def test_compose_api_is_hardened_and_localhost_only() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    api = compose["services"]["api"]
    assert api["network_mode"] == "host"
    assert api["read_only"] is True
    assert api["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in api["security_opt"]
    assert "/var/run/docker.sock" not in str(api.get("volumes", []))
    assert api["user"] == "10001:20"
    assert "devices" not in api
    assert (
        "/sys/firmware/devicetree/base:/run/kronoskvm/device-tree:ro"
        in api["volumes"]
    )


def test_boot_service_does_not_pin_a_stale_image_version() -> None:
    unit = Path("deploy/systemd/kronoskvm-containers.service").read_text(
        encoding="utf-8"
    )
    assert "Environment=KRONOSKVM_VERSION=" not in unit


def test_container_runs_as_non_root() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    assert "USER 10001:20" in dockerfile
    assert '--host", "127.0.0.1"' in dockerfile
    assert "HEALTHCHECK" in dockerfile


def test_web_assets_use_filename_versioning() -> None:
    html = Path("frontend/src/index.html").read_text(encoding="utf-8")
    dockerfile = Path("Dockerfile.web").read_text(encoding="utf-8")
    assert "/app-0.3.0.js" in html
    assert "/styles-0.3.0.css" in html
    assert "app-0.3.0.js" in dockerfile
    assert 'id="terminal-layer"' in html
    app = Path("frontend/src/app.js").read_text(encoding="utf-8")
    assert "const terminals = new Map()" in app
    assert "startTerminalLog" in app
    assert "downloadTerminalLog" in app
    assert 'class="metrics"' not in html
    assert 'class="port-table"' in html
    assert 'class="action-menu"' in Path("frontend/src/app.js").read_text(
        encoding="utf-8"
    )
    assert "/kronoskvm-logo.png" in html
    assert 'data-theme-choice="light"' in html
    assert 'data-theme-choice="dark"' in html
    assert 'class="side-nav"' in html
    assert 'class="session-strip collapsible"' in html
    assert 'localStorage.getItem(themeStorageKey) || "light"' in app
    assert 'data-collapse-id="physical-ports-v2"' in html
    assert 'data-collapse-id="appliance-status-v2"' in html
    assert html.count('data-collapse-group="hardware-details"') == 2
    assert html.count('data-default-collapsed="true"') == 2
    assert "function setCollapsed" in app


def test_web_gateway_is_hardened_and_ap_only() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    web = compose["services"]["web"]
    nginx = Path("deploy/nginx/nginx.conf").read_text(encoding="utf-8")
    assert web["network_mode"] == "host"
    assert web["read_only"] is True
    assert web["cap_drop"] == ["ALL"]
    assert web["cap_add"] == ["CHOWN", "NET_BIND_SERVICE", "SETGID", "SETUID"]
    assert "no-new-privileges:true" in web["security_opt"]
    assert "listen 192.168.34.100:80;" in nginx
    assert "listen 80" not in nginx
    assert "proxy_pass http://127.0.0.1:8000;" in nginx
    assert 'proxy_set_header Upgrade $http_upgrade;' in nginx
    assert 'Cache-Control "no-store, no-cache, must-revalidate"' in nginx


def test_docker_daemon_does_not_manage_routing() -> None:
    daemon = json.loads(
        Path("deploy/docker/daemon.json").read_text(encoding="utf-8")
    )
    assert daemon["bridge"] == "none"
    assert daemon["iptables"] is False
    assert daemon["ip-forward"] is False
    assert daemon["ip-masq"] is False
