import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import server


class PasswordTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "config.json")
        self.config = {"password_hash": server.hash_password("old-test-password"), "token_secret": "a" * 64}
        Path(self.path).write_text(json.dumps(self.config))
        self.patcher = patch.object(server, "CONFIG_PATH", self.path)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_change_persists_and_invalidates_old_tokens(self):
        token, _ = server.make_token(self.config["token_secret"])
        server.change_management_password(self.config, "old-test-password", "1", "1")
        self.assertFalse(server.verify_token(self.config["token_secret"], token))
        self.assertTrue(server.check_password("1", server.load_config()["password_hash"]))
        self.assertFalse(server.check_password("old-test-password", self.config["password_hash"]))

    def test_invalid_changes_preserve_config(self):
        original = Path(self.path).read_text()
        for current, new, confirmation in (("wrong", "1", "1"), ("old-test-password", "", ""), ("old-test-password", "x", "y")):
            with self.assertRaises(ValueError):
                server.change_management_password(self.config, current, new, confirmation)
            self.assertEqual(Path(self.path).read_text(), original)

    def test_write_failure_keeps_old_password(self):
        original = dict(self.config)
        with patch.object(server.os, "replace", side_effect=OSError("test")), self.assertRaises(OSError):
            server.change_management_password(self.config, "old-test-password", "abc", "abc")
        self.assertEqual(self.config, original)
        self.assertEqual(json.loads(Path(self.path).read_text()), original)

    def test_douban_credentials_are_not_changed(self):
        douban = Path(self.temp.name) / "douban_session.json"
        douban.write_text('{"cookies":"test-only"}')
        server.change_management_password(self.config, "old-test-password", "中文", "中文")
        self.assertEqual(douban.read_text(), '{"cookies":"test-only"}')

    def test_http_change_requires_login_and_logs_out_all_tokens(self):
        config = self.config
        class Handler(server.Handler):
            def log_message(self, *args):
                pass
        Handler.config = config
        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=httpd.serve_forever, daemon=True)
        worker.start()
        def call(path, data=None, token=None):
            client = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=3)
            headers = {"Content-Type": "application/json"}
            if token:
                headers["Authorization"] = "Bearer " + token
            client.request("POST" if data is not None else "GET", path, json.dumps(data) if data is not None else None, headers)
            response = client.getresponse()
            status, result = response.status, json.loads(response.read())
            client.close()
            return status, result
        try:
            server.FAILS.clear()
            self.assertEqual(call("/api/password", {})[0], 401)
            status, result = call("/api/login", {"password": "old-test-password"})
            self.assertEqual(status, 200)
            token = result["token"]
            self.assertEqual(call("/api/password", {"current_password": "wrong", "new_password": "x", "confirm_password": "x"}, token)[0], 400)
            self.assertEqual(call("/api/me", token=token)[0], 200)
            self.assertEqual(call("/api/password", {"current_password": "old-test-password", "new_password": "1", "confirm_password": "1"}, token)[0], 200)
            self.assertEqual(call("/api/me", token=token)[0], 401)
            self.assertEqual(call("/api/login", {"password": "1"})[0], 200)
        finally:
            httpd.shutdown()
            httpd.server_close()
            worker.join(2)
            server.FAILS.clear()


if __name__ == "__main__":
    unittest.main()
