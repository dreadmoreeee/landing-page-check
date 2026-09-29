import os
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FORBIDDEN_PORTS = {8765, 8737, 8787}


class Site:
    """A local HTTP server on a random free port. `routes` maps a path to
    (status, headers, body) or to a callable(query) returning that tuple."""

    def __init__(self):
        self.routes = {}
        self.hits = []
        site = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                parts = urlsplit(self.path)
                site.hits.append(self.path)
                route = site.routes.get(parts.path)
                if route is None:
                    status, headers, body = 404, {}, "not found"
                elif callable(route):
                    status, headers, body = route(parts.query)
                else:
                    status, headers, body = route
                data = body.encode("utf-8") if isinstance(body, str) else body
                self.send_response(status)
                headers = dict(headers)
                headers.setdefault("Content-Type", "text/html; charset=utf-8")
                for k, v in headers.items():
                    for one in (v if isinstance(v, list) else [v]):
                        self.send_header(k, one)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        while True:
            self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            if self.server.server_address[1] not in FORBIDDEN_PORTS:
                break
            self.server.server_close()
        self.port = self.server.server_address[1]
        self.base = "http://127.0.0.1:%d" % self.port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def page(self, path, html, status=200, headers=None):
        self.routes[path] = (status, headers or {}, html)

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def site():
    s = Site()
    yield s
    s.close()


@pytest.fixture
def site2():
    s = Site()
    yield s
    s.close()


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()

