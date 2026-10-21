"""Loopback asset server shared by Studio and browser renderers."""
from http.server import ThreadingHTTPServer


class LocalHTTPServer(ThreadingHTTPServer):
    # Chromium opens asset connections in bursts. Python 3.11/3.12's default
    # backlog of five can refuse connections on Windows while the accept loop
    # is busy starting handler threads. Queue the burst instead of losing JS
    # modules; this changes neither routing nor the handlers' access checks.
    request_queue_size = 128
