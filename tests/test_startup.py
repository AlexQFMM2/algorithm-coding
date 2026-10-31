import contextlib
import io
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from workbench.server import Server, main


class StartupTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="acwing-startup-")
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def serve(self, server):
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def cleanup():
            server.shutdown()
            server.server_close()
            thread.join()

        self.addCleanup(cleanup)
        return server.server_port

    def test_repeat_start_opens_existing_workspace_without_new_server(self):
        port = self.serve(Server(self.root, 0))
        for no_browser in (False, True):
            with self.subTest(no_browser=no_browser):
                argv = ["app.py", "--root", str(self.root), "--port", str(port)]
                if no_browser:
                    argv.append("--no-browser")
                with patch("sys.argv", argv), patch("workbench.server.webbrowser.open") as browser:
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        main()
                    self.assertIn("已使用现有服务", output.getvalue())
                    if no_browser:
                        browser.assert_not_called()
                    else:
                        browser.assert_called_once_with(f"http://127.0.0.1:{port}")

    def assert_port_conflict(self, port, root):
        argv = ["app.py", "--root", str(root), "--port", str(port)]
        with patch("sys.argv", argv), patch("workbench.server.webbrowser.open") as browser:
            output = io.StringIO()
            with contextlib.redirect_stderr(output), self.assertRaises(SystemExit) as caught:
                main()
            self.assertEqual(caught.exception.code, 1)
            self.assertIn(f"端口 {port}", output.getvalue())
            self.assertIn("./start.sh --port", output.getvalue())
            browser.assert_not_called()

    def test_different_repository_is_not_reused(self):
        port = self.serve(Server(self.root, 0))
        other_root = self.root / "another-repository"
        other_root.mkdir()
        self.assert_port_conflict(port, other_root)

    def test_unrelated_service_is_not_reused_or_stopped(self):
        class UnrelatedHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                content = json.dumps({"ok": True}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), UnrelatedHandler)
        port = self.serve(server)
        self.assert_port_conflict(port, self.root)
        self.assertNotEqual(server.fileno(), -1)


if __name__ == "__main__":
    unittest.main()
