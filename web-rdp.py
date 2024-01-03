import logging
import ssl
from pathlib import Path

import aiohttp
import aiohttp.web

from auth import make_auth_middleware
from config import Config, parse_args
from inputs import ScreenInfo, create_backend, load_allowed_keys
from ws import ALLOWED_KEYS, INPUT_BACKEND, SCREEN, inputWS, streamWS

# Resolve assets next to this file so the server works from any directory
SRC_DIR = Path(__file__).resolve().parent / "src"

# Files served to the browser: url path -> (file name, content type)
STATIC_FILES = {
    "/": ("stream.html", "text/html"),
    "/script.js": ("script.js", "application/javascript"),
    "/style.css": ("style.css", "text/css"),
    "/keys.json": ("keys.json", "application/json"),
}


def make_static_handler(file_name: str, content_type: str):
    path = SRC_DIR / file_name

    async def handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
        return aiohttp.web.Response(
            body=path.read_bytes(),
            content_type=content_type,
            charset="utf-8",
            headers={"Cache-Control": "no-cache"},
        )

    return handler


def make_app(config: Config, input_backend=None) -> aiohttp.web.Application:
    app = aiohttp.web.Application(
        middlewares=[make_auth_middleware(config.username, config.password)]
    )

    # State shared with the websocket handlers
    app[SCREEN] = ScreenInfo()
    app[ALLOWED_KEYS] = load_allowed_keys(SRC_DIR / "keys.json")
    app[INPUT_BACKEND] = input_backend or create_backend()

    for url, (file_name, content_type) in STATIC_FILES.items():
        app.router.add_get(url, make_static_handler(file_name, content_type))

    app.router.add_get("/inputWS", inputWS)
    app.router.add_get("/streamWS", streamWS)
    return app


def make_ssl_context(config: Config):
    if not config.tls:
        return None
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(config.cert, config.key)
    return context


def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    config = parse_args()
    scheme = "https" if config.tls else "http"

    print(f"web-rdp listening on {scheme}://{config.host}:{config.port}")
    print(f"  user:     {config.username}")
    if config.password_generated:
        print(f"  password: {config.password}  (generated, pass --password to set your own)")
    if not config.tls:
        print("  warning:  traffic is not encrypted, use --cert/--key outside trusted networks")

    aiohttp.web.run_app(
        make_app(config),
        host=config.host,
        port=config.port,
        ssl_context=make_ssl_context(config),
        print=None,
    )


if __name__ == "__main__":
    main()
