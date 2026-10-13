import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from datetime import timedelta, timezone
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch, MagicMock

from werkzeug.security import generate_password_hash
from server import Store, ZONE, create_app, scheduler_tick, send_wecom
from setup_auth import password_is_valid

PASSWORD = "183602"
HASH = generate_password_hash(PASSWORD)


class ReminderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test-session-key",
                               "PASSWORD_HASH": HASH, "DATA_DIR": self.temp.name,
                               "AUTH_FILE": str(Path(self.temp.name) / "auth.json"),
                               "SESSION_COOKIE_SECURE": False})
        self.client = self.app.test_client()
        self.store = self.app.extensions["store"]
        self.csrf = self.client.get("/api/session").json["csrf"]

    def call(self, path, method="POST", data=None):
        return self.client.open(path, method=method, json=data or {}, headers={"X-CSRF-Token": self.csrf})

    def login(self):
        result = self.call("/api/login", data={"password": PASSWORD})
        self.assertEqual(result.status_code, 200)
        self.csrf = result.json["csrf"]

    def create(self, **changes):
        data = {"content": "喝水", "time": "09:00", "rule": {"type": "daily"}, "channels": ["browser"]}
        data.update(changes)
        return self.call("/api/reminders", data=data)

    def test_all_data_and_actions_require_login(self):
        for path, method in [("/api/reminders", "GET"), ("/api/settings", "GET"),
                             ("/api/poll", "GET"), ("/api/reminders", "POST"),
                             ("/api/settings", "PUT"), ("/api/fire", "POST"),
                             ("/api/test", "POST"), ("/api/password", "POST"), ("/api/reminders/123", "DELETE")]:
            self.assertEqual(self.call(path, method).status_code, 401)

    def test_login_csrf_logout_and_cookie(self):
        self.assertEqual(self.client.post("/api/login", json={"password": PASSWORD}).status_code, 403)
        self.assertEqual(self.call("/api/login", data={"password": "wrong"}).status_code, 401)
        self.login()
        self.assertEqual(self.client.post("/api/reminders", json={}).status_code, 403)
        self.assertEqual(self.call("/api/logout").status_code, 200)
        self.assertEqual(self.client.get("/api/settings").status_code, 401)
        self.app.config["SESSION_COOKIE_SECURE"] = True
        result = self.app.test_client().get("/api/session")
        cookie = result.headers["Set-Cookie"]
        for flag in ("Secure", "HttpOnly", "SameSite=Strict"):
            self.assertIn(flag, cookie)

    def test_login_rate_limit(self):
        for _ in range(10):
            self.assertEqual(self.call("/api/login", data={"password": "wrong"}).status_code, 401)
        self.assertEqual(self.call("/api/login", data={"password": PASSWORD}).status_code, 429)

    def test_password_has_no_length_or_format_policy(self):
        for password in ("1", "123456", "abc", "中文 密码", "１２３４５６", " " , "x" * 1000):
            self.assertTrue(password_is_valid(password))
        for password in ("", None, 123):
            self.assertFalse(password_is_valid(password))

    def test_password_change_persists_and_logs_out_all_devices(self):
        self.login()
        old_cookie = self.client.get_cookie("reminder_session")
        result = self.call("/api/password", data={"current_password": PASSWORD, "new_password": "1", "confirm_password": "1"})
        self.assertEqual(result.status_code, 200)
        self.assertNotIn("csrf", result.json)
        self.assertEqual(self.client.get("/api/reminders").status_code, 401)
        self.assertFalse(self.client.get("/api/session").json["authenticated"])
        other = self.app.test_client()
        other.set_cookie("reminder_session", old_cookie.value)
        self.assertEqual(other.get("/api/reminders").status_code, 401)
        self.assertFalse(other.get("/api/session").json["authenticated"])
        auth_path = Path(self.temp.name) / "auth.json"
        saved = json.loads(auth_path.read_text())
        self.assertNotEqual(saved["password_hash"], "1")
        recreated = create_app({"TESTING": True, "AUTH_FILE": str(auth_path), "DATA_DIR": self.temp.name,
                                "SESSION_COOKIE_SECURE": False})
        client = recreated.test_client()
        csrf = client.get("/api/session").json["csrf"]
        self.assertEqual(client.post("/api/login", json={"password": PASSWORD}, headers={"X-CSRF-Token": csrf}).status_code, 401)
        self.assertEqual(client.post("/api/login", json={"password": "1"}, headers={"X-CSRF-Token": csrf}).status_code, 200)

    def test_password_change_validates_without_losing_current_login(self):
        self.login()
        for current, new, confirm in (("wrong", "abc", "abc"), (PASSWORD, "", ""), (PASSWORD, "abc", "xyz")):
            result = self.call("/api/password", data={"current_password": current, "new_password": new, "confirm_password": confirm})
            self.assertEqual(result.status_code, 400)
            self.assertEqual(self.client.get("/api/reminders").status_code, 200)
        self.assertEqual(self.client.post("/api/password", json={}).status_code, 403)
        self.assertFalse((Path(self.temp.name) / "auth.json").exists())

    def test_password_write_failure_preserves_existing_password(self):
        self.login()
        with patch("server.atomic_json", side_effect=OSError("test write failure")), self.assertLogs(level="ERROR"):
            result = self.call("/api/password", data={"current_password": PASSWORD, "new_password": "abc", "confirm_password": "abc"})
        self.assertEqual(result.status_code, 500)
        self.assertEqual(self.app.config["PASSWORD_HASH"], HASH)
        self.assertEqual(self.client.get("/api/reminders").status_code, 200)

    def test_persistent_login_survives_browser_and_service_restart(self):
        self.login()
        self.assertEqual(self.app.config["PERMANENT_SESSION_LIFETIME"], timedelta(days=30))
        cookie = self.client.get_cookie("reminder_session")
        recreated = create_app({"TESTING": True, "SECRET_KEY": "test-session-key", "PASSWORD_HASH": HASH,
                                "DATA_DIR": self.temp.name, "SESSION_COOKIE_SECURE": False})
        reopened = recreated.test_client()
        reopened.set_cookie("reminder_session", cookie.value)
        result = reopened.get("/api/reminders")
        self.assertEqual(result.status_code, 200)
        self.assertIn("Set-Cookie", result.headers, "Activity should renew the persistent login")
        header = SimpleCookie(result.headers["Set-Cookie"])
        expiration = parsedate_to_datetime(header["reminder_session"]["expires"])
        self.assertGreater(expiration - datetime.now(timezone.utc), timedelta(days=29))

    def test_crud_validation_and_persistence(self):
        self.login()
        created = self.create()
        self.assertEqual(created.status_code, 201)
        rid = created.json["id"]
        self.assertEqual(self.call("/api/reminders/" + rid, "PUT", {"content": "起身"}).json["content"], "起身")
        self.assertEqual(Store(self.temp.name).read("reminders", [])[0]["content"], "起身")
        for changes in ({"time": "25:00"}, {"channels": ["unknown"]}, {"rule": {"type": "weekly", "days": [8]}},
                        {"rule": {"type": "once", "date": "2026-02-30"}}, {"content": ""}):
            self.assertEqual(self.create(**changes).status_code, 400)
        self.assertEqual(self.call("/api/reminders/" + rid, "DELETE").status_code, 200)
        self.assertEqual(self.client.get("/api/reminders").json, [])

    def test_secret_never_returned_and_blank_preserves_it(self):
        self.login()
        saved = self.call("/api/settings", "PUT", {"email": {"auth_code": "private-mail-secret"}})
        self.assertNotIn("private-mail-secret", saved.text)
        self.assertNotIn("auth_code", saved.json["email"])
        self.assertTrue(saved.json["email"]["auth_code_configured"])
        self.call("/api/settings", "PUT", {"email": {"auth_code": "", "account": "owner@example.com"}})
        self.assertEqual(self.store.settings()["email"]["auth_code"], "private-mail-secret")
        self.assertNotIn("private-mail-secret", self.client.get("/api/settings").text)

    def test_legacy_files_still_load(self):
        self.store.write("settings", {"email": {"auth_code": "legacy"}, "wecom": {"webhook": "old"}})
        self.store.write("reminders", [{"id": "abcd1234", "content": "旧提醒", "time": "09:00",
                                        "enabled": True, "channels": ["browser"], "rule": {"type": "daily"}}])
        self.login()
        self.assertEqual(self.client.get("/api/reminders").json[0]["id"], "abcd1234")
        self.assertTrue(self.client.get("/api/settings").json["email"]["auth_code_configured"])

    def test_wecom_setting_preserves_secret_and_other_channels(self):
        self.login()
        webhook = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test-key"
        response = self.call("/api/settings", "PUT", {"wecom": {"webhook": webhook}})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["wecom"]["webhook_configured"])
        self.assertNotIn(webhook, response.text)
        self.assertNotIn("webhook", response.json["wecom"])
        self.call("/api/settings", "PUT", {"email": {"account": "owner@example.com"}})
        self.call("/api/settings", "PUT", {"wecom": {"webhook": ""}})
        self.assertEqual(self.store.settings()["wecom"]["webhook"], webhook)
        self.assertEqual(self.store.settings()["email"]["account"], "owner@example.com")
        for invalid in ("http://127.0.0.1/", "https://example.com/", "https://qyapi.weixin.qq.com.evil.invalid/cgi-bin/webhook/send?key=x", []):
            self.assertEqual(self.call("/api/settings", "PUT", {"wecom": {"webhook": invalid}}).status_code, 400)
        self.assertEqual(self.store.settings()["wecom"]["webhook"], webhook)

    def test_wecom_test_manual_and_scheduled_notifications(self):
        self.login()
        self.call("/api/settings", "PUT", {"wecom": {"webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test-key"}})
        created = self.create(channels=["wecom"])
        self.assertEqual(created.status_code, 201)
        with patch("server.send_wecom", return_value=(True, "")) as sender:
            self.assertTrue(self.call("/api/test", data={"channel": "wecom"}).json["ok"])
            self.assertTrue(self.call("/api/fire", data={"id": created.json["id"]}).json["results"]["wecom"]["ok"])
            self.assertEqual(scheduler_tick(self.store, datetime(2026, 10, 13, 9, 0, tzinfo=ZONE)), 1)
            self.assertEqual(sender.call_count, 3)

    def test_wecom_payload_and_sanitized_errors(self):
        settings = self.store.settings()
        self.assertFalse(send_wecom("提醒", settings)[0])
        settings["wecom"]["webhook"] = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=secret-test-key"
        opener = MagicMock()
        response = opener.open.return_value.__enter__.return_value
        response.read.return_value = b'{"errcode":0,"errmsg":"ok"}'
        with patch("server.urllib.request.build_opener", return_value=opener):
            self.assertEqual(send_wecom("喝水", settings), (True, ""))
            req = opener.open.call_args.args[0]
            self.assertEqual(json.loads(req.data), {"msgtype": "text", "text": {"content": "喝水"}})
            self.assertEqual(req.method, "POST")
            response.read.return_value = b'{"errcode":93000,"errmsg":"secret-test-key"}'
            ok, message = send_wecom("提醒", settings)
            self.assertFalse(ok)
            self.assertIn("93000", message)
            self.assertNotIn("secret-test-key", message)
            opener.open.side_effect = OSError(settings["wecom"]["webhook"])
            self.assertNotIn("secret-test-key", send_wecom("提醒", settings)[1])

    def test_reminders_require_all_selected_channels_to_be_configured(self):
        self.login()
        flags = self.client.get("/api/settings").json
        self.assertFalse(flags["email"]["configured"])
        self.assertFalse(flags["wecom"]["configured"])
        for channels in (["email"], ["wecom"], ["browser", "email", "wecom"]):
            result = self.create(channels=channels)
            self.assertEqual(result.status_code, 400)
            self.assertIn("尚未配置完整", result.json["error"])
        self.assertEqual(self.client.get("/api/reminders").json, [])
        self.call("/api/settings", "PUT", {"email": {"account": "sender@example.com"}})
        self.assertEqual(self.create(channels=["email"]).status_code, 400)
        self.call("/api/settings", "PUT", {"email": {"auth_code": "test-code", "to": "receiver@example.com"},
                                                "wecom": {"webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test-key"}})
        flags = self.client.get("/api/settings").json
        self.assertTrue(flags["email"]["configured"])
        self.assertTrue(flags["wecom"]["configured"])
        self.assertEqual(self.create(channels=["email", "wecom"]).status_code, 201)

    def test_edit_and_enable_check_configuration_without_losing_old_reminder(self):
        self.login()
        rid = self.create().json["id"]
        self.assertEqual(self.call("/api/reminders/" + rid, "PUT", {"channels": ["wecom"]}).status_code, 400)
        self.assertEqual(self.client.get("/api/reminders").json[0]["channels"], ["browser"])
        self.assertEqual(self.call("/api/reminders/" + rid, "PUT", {"enabled": False, "channels": ["wecom"]}).status_code, 200)
        self.assertEqual(self.call("/api/reminders/" + rid, "PUT", {"enabled": True}).status_code, 400)
        self.assertFalse(self.client.get("/api/reminders").json[0]["enabled"])

    def test_browser_scheduler_does_not_deadlock_or_duplicate(self):
        self.login()
        self.create()
        now = datetime(2026, 10, 13, 9, 0, tzinfo=ZONE)
        thread = threading.Thread(target=scheduler_tick, args=(self.store, now), daemon=True)
        thread.start()
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive(), "Scheduler deadlocked")
        self.assertEqual(len(self.store.events), 1)
        self.assertEqual(scheduler_tick(self.store, now), 0)
        self.assertEqual(scheduler_tick(Store(self.temp.name), now), 0)

    def test_same_second_events_and_restart_cursor(self):
        self.login()
        first = self.client.get("/api/poll").json
        for _ in range(2):
            self.call("/api/test", data={"channel": "browser"})
        result = self.client.get("/api/poll", query_string={"since": first["cursor"], "epoch": first["epoch"]}).json
        self.assertEqual(len(result["events"]), 2)
        self.assertEqual(len(self.client.get("/api/poll", query_string={"since": result["cursor"], "epoch": result["epoch"]}).json["events"]), 0)
        self.assertEqual(self.client.get("/api/poll?since=999&epoch=old").json["cursor"], 2)

    def test_sending_email_does_not_hold_data_lock(self):
        self.login()
        self.call("/api/settings", "PUT", {"email": {"account": "sender@example.com", "auth_code": "test-code", "to": "receiver@example.com"}})
        self.create(channels=["email"])
        entered, release = threading.Event(), threading.Event()
        def slow_email(*args):
            entered.set()
            release.wait(3)
            return True, ""
        with patch("server.send_email", side_effect=slow_email):
            thread = threading.Thread(target=scheduler_tick, args=(self.store, datetime(2026, 10, 13, 9, 0, tzinfo=ZONE)))
            thread.start()
            try:
                self.assertTrue(entered.wait(2))
                acquired = self.store.lock.acquire(timeout=0.5)
                self.assertTrue(acquired)
                if acquired:
                    self.store.lock.release()
            finally:
                release.set()
                thread.join(3)

    def test_concurrent_creates_are_not_lost(self):
        self.login()
        with self.client.session_transaction() as session:
            values = dict(session)
        def create_one(index):
            client = self.app.test_client()
            with client.session_transaction() as session:
                session.update(values)
            return client.post("/api/reminders", json={"content": str(index), "time": "09:00", "rule": {"type": "daily"},
                                                       "channels": ["browser"]}, headers={"X-CSRF-Token": self.csrf}).status_code
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(list(pool.map(create_one, range(20))), [201] * 20)
        self.assertEqual(len(self.store.read("reminders", [])), 20)

    def test_bad_data_is_not_overwritten(self):
        self.login()
        path = Path(self.temp.name) / "reminders.json"
        path.write_text("invalid-json", encoding="utf-8")
        with self.assertLogs(level="ERROR"):
            self.assertEqual(self.create().status_code, 500)
        self.assertEqual(path.read_text(), "invalid-json")


if __name__ == "__main__":
    unittest.main()
