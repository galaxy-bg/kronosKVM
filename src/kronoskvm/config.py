import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppConfig:
    host: str = "127.0.0.1"
    port: int = 8080


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        return AppConfig()

    with config_path.open("rb") as file:
        data = tomllib.load(file)

    server = data.get("server", {})
    defaults = AppConfig()
    return AppConfig(
        host=str(server.get("host", defaults.host)),
        port=int(server.get("port", defaults.port)),
    )
