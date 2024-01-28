"""Command line / environment configuration."""

import argparse
import os
import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Optional

DEFAULT_PORT = 7417


@dataclass
class Config:
    host: str = "0.0.0.0"
    port: int = DEFAULT_PORT
    username: str = "admin"
    password: str = ""
    cert: Optional[str] = None
    key: Optional[str] = None
    password_generated: bool = False

    @property
    def tls(self) -> bool:
        return bool(self.cert and self.key)


def parse_args(argv: Optional[Sequence[str]] = None) -> Config:
    parser = argparse.ArgumentParser(
        prog="web-rdp", description="Control this computer from a web browser."
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("WEB_RDP_HOST", "0.0.0.0"),
        help="address to listen on (default: 0.0.0.0, use 127.0.0.1 for local only)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("WEB_RDP_PORT", DEFAULT_PORT)),
        help=f"port to listen on (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--username",
        default=os.environ.get("WEB_RDP_USERNAME", "admin"),
        help="login user name (default: admin)",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("WEB_RDP_PASSWORD", ""),
        help="login password (default: random, printed on startup)",
    )
    parser.add_argument("--cert", help="TLS certificate file (enables https/wss)")
    parser.add_argument("--key", help="TLS private key file")

    args = parser.parse_args(argv)

    if not 0 < args.port < 65536:
        parser.error("--port must be between 1 and 65535")
    if bool(args.cert) != bool(args.key):
        parser.error("--cert and --key must be given together")

    config = Config(
        host=args.host,
        port=args.port,
        username=args.username,
        password=args.password,
        cert=args.cert,
        key=args.key,
    )

    if not config.password:
        config.password = secrets.token_urlsafe(12)
        config.password_generated = True

    return config
