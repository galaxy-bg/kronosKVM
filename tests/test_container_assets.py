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
    assert "/mnt/kronoskvm-storage:/storage" in api["volumes"]
    assert api["environment"]["KRONOSKVM_STORAGE_PATH"] == "/storage"
    assert api["environment"]["KRONOSKVM_STORAGE_REQUIRE_MARKER"] == "1"


def test_boot_service_does_not_pin_a_stale_image_version() -> None:
    unit = Path("deploy/systemd/kronoskvm-containers.service").read_text(
        encoding="utf-8"
    )
    assert "Environment=KRONOSKVM_VERSION=" not in unit
    assert "ExecStartPre=/usr/bin/install -d -m 0755 -o root -g root /mnt/kronoskvm-storage" in unit
    assert "ExecStart=/opt/kronoskvm/scripts/start-containers.sh" in unit


def test_runtime_grants_only_usb_serial_device_class() -> None:
    runner = Path("scripts/start-containers.sh").read_text(encoding="utf-8")
    assert "--device-cgroup-rule 'c 188:* rmw'" in runner
    assert "--volume /dev:/dev:rw" in runner
    assert "--user 10001:20" in runner
    assert "--cap-drop ALL" in runner
    assert "--privileged" not in runner


def test_container_runs_as_non_root() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    assert "USER 10001:20" in dockerfile
    assert '--host", "127.0.0.1"' in dockerfile
    assert "HEALTHCHECK" in dockerfile


def test_web_assets_use_filename_versioning() -> None:
    html = Path("frontend/src/index.html").read_text(encoding="utf-8")
    dockerfile = Path("Dockerfile.web").read_text(encoding="utf-8")
    assert "/app-0.3.8.js" in html
    assert "/styles-0.3.8.css" in html
    assert "app-0.3.8.js" in dockerfile
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
    assert html.count('data-default-collapsed="true"') == 3
    assert 'class="header-brand"' in html
    assert "header-brand-mark" not in html
    assert "Remote Console Toolkit" in html
    assert "All-in-One IP-KVM System" in html
    assert html.index('id="new-session"') > html.index('id="active-sessions-title"')
    assert "function setCollapsed" in app
    assert 'id="storage-panel"' in html
    assert 'id="storage-file-input"' in html
    assert 'getJson("/api/v1/storage")' in app
    assert '.filter((item) => item.name !== "lo")' in app
    assert 'data-session-action="config"' in html
    assert "function updateSessionCards" in app
    assert 'class="workspace-grid"' not in html
    assert 'class="quick-actions"' not in html
    assert 'class="notice"' not in html
    assert "Workspaces" not in html
    assert "Profiles" not in html
    assert "Manage sessions" in html
    assert "Console 1 · USB" in html
    styles = Path("frontend/src/styles.css").read_text(encoding="utf-8")
    assert ".action-menu:hover .action-menu-list" not in styles
    assert 'data-connection-type="ssh"' in html
    assert 'data-connection-type="telnet"' in html
    assert 'data-connection-type="rdp"' in html
    assert 'data-connection-type="vnc"' in html
    assert 'data-connection-type="web"' in html
    assert 'getJson("/api/v1/connections")' in app
    assert 'new WebSocket(`${protocol}://${location.host}/api/v1/ssh/ws`)' in app
    assert "Delete connection" in app


def test_web_gateway_is_hardened_and_ap_only() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    web = compose["services"]["web"]
    nginx = Path("deploy/nginx/nginx.conf").read_text(encoding="utf-8")
    assert web["network_mode"] == "host"
    assert web["read_only"] is True
    assert web["cap_drop"] == ["ALL"]
    assert web["cap_add"] == ["CHOWN", "NET_BIND_SERVICE", "SETGID", "SETUID"]
    assert "no-new-privileges:true" in web["security_opt"]
    assert "listen 0.0.0.0:80 default_server;" in nginx
    assert "proxy_pass http://127.0.0.1:8000;" in nginx
    assert 'proxy_set_header Upgrade $http_upgrade;' in nginx
    assert 'Cache-Control "no-store, no-cache, must-revalidate"' in nginx
    assert "client_max_body_size 16g;" in nginx
    assert "proxy_request_buffering off;" in nginx
    assert "listen 127.0.0.1:8000" not in nginx


def test_docker_daemon_does_not_manage_routing() -> None:
    daemon = json.loads(
        Path("deploy/docker/daemon.json").read_text(encoding="utf-8")
    )
    assert daemon["bridge"] == "none"
    assert daemon["iptables"] is False
    assert daemon["ip-forward"] is False
    assert daemon["ip-masq"] is False
