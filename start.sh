#!/usr/bin/env bash
# Start web-rdp on macOS / Linux (X11). Extra arguments are passed to the server.
cd "$(dirname "$0")" || exit 1
exec python3 web-rdp.py "$@"
