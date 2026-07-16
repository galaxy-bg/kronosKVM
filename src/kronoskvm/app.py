from aiohttp import web

from kronoskvm import __version__
from kronoskvm.config import AppConfig
from kronoskvm.system import get_system_info


async def health(_request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "version": __version__})


async def system_info(_request: web.Request) -> web.Response:
    return web.json_response(get_system_info())


def create_app(config: AppConfig | None = None) -> web.Application:
    app = web.Application()
    app["config"] = config or AppConfig()
    app.router.add_get("/health", health)
    app.router.add_get("/api/v1/system", system_info)
    return app
