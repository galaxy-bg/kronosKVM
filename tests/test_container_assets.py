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


def test_container_runs_as_non_root() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    assert "USER 10001:10001" in dockerfile
    assert '--host", "127.0.0.1"' in dockerfile
    assert "HEALTHCHECK" in dockerfile


def test_docker_daemon_does_not_manage_routing() -> None:
    daemon = json.loads(
        Path("deploy/docker/daemon.json").read_text(encoding="utf-8")
    )
    assert daemon["bridge"] == "none"
    assert daemon["iptables"] is False
    assert daemon["ip-forward"] is False
    assert daemon["ip-masq"] is False
