"""Asset connections must survive a temporarily busy server accept loop."""
from functools import partial
from http.client import HTTPResponse
from pathlib import Path
import socket
import tempfile
import threading
import unittest

from openkatana.http_runtime import LocalHTTPServer
from openkatana.render import Handler


class AssetServerTests(unittest.TestCase):
    def test_asset_burst_queues_until_accept_loop_resumes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = b'window.assetLoaded = true;\n'
            (root / 'asset.js').write_bytes(payload)
            server = LocalHTTPServer(('127.0.0.1', 0), partial(Handler, project=root))
            clients = []
            thread = None
            try:
                # Pause accepting to reproduce a busy renderer under CPU load.
                # All handshakes must queue, without relying on HTTP retries.
                for _ in range(24):
                    client = socket.create_connection(server.server_address, timeout=2)
                    clients.append(client)
                    client.sendall(b'GET /project/asset.js HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n')
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                for client in clients:
                    client.settimeout(10)
                    with HTTPResponse(client) as response:
                        response.begin()
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.read(), payload)
                        self.assertIn("default-src 'self'", response.getheader('Content-Security-Policy'))
            finally:
                for client in clients:
                    client.close()
                if thread is not None:
                    server.shutdown()
                    thread.join()
                server.server_close()
