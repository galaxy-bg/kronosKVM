#!/usr/bin/env python3
"""Read-only HTTP recovery download server; logs requests to the journal."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


class RecoveryHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        parts = unquote(urlsplit(self.path).path).split("/")
        target = Path(self.directory)
        for part in parts:
            if not part:
                continue
            if part.startswith(".") or "\\" in part:
                self.send_error(404)
                return None
            target = target / part
            if target.is_symlink():
                self.send_error(404)
                return None
        if not target.is_file():
            self.send_error(404)
            return None
        return super().send_head()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Disposition", "attachment")
        super().end_headers()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", default="192.168.34.100")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--directory", default="/mnt/kronoskvm-storage/recovery")
    args = parser.parse_args()
    server = ThreadingHTTPServer(
        (args.bind, args.port), partial(RecoveryHandler, directory=args.directory)
    )
    print(f"Recovery HTTP listening on {args.bind}:{args.port}", flush=True)
    server.serve_forever()
