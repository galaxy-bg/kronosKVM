import argparse

from aiohttp import web

from kronoskvm.app import create_app
from kronoskvm.config import load_config


def main() -> None:
    parser = argparse.ArgumentParser(description="KronosKVM control service")
    parser.add_argument(
        "--config",
        default="/etc/kronoskvm/config.toml",
        help="Path to the TOML configuration file",
    )
    args = parser.parse_args()
    config = load_config(args.config)
    web.run_app(create_app(config), host=config.host, port=config.port)


if __name__ == "__main__":
    main()
