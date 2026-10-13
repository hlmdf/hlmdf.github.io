"""Single-owner reminder service. Run python server.py (one process only)."""
import copy
import json
import logging
import os
from pathlib import Path
import re
import secrets
import smtplib
import ssl
import tempfile
import threading
import time
import uuid
import urllib.request
from datetime import datetime, timedelta
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from flask import Flask, abort, jsonify, request, send_file, session
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

BASE = Path(__file__).resolve().parent
ZONE = ZoneInfo("Asia/Shanghai")
DEFAULT_SETTINGS = {"email": {"smtp_host": "smtp.qq.com", "smtp_port": 465,
                              "account": "", "auth_code": "", "to": ""},
                    "wecom": {"webhook": ""}}


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".write-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.lock = threading.RLock()
        self.events = []
        # A new epoch on restart lets open pages reset their cursor safely.
        self.epoch = uuid.uuid4().hex
        self.sequence = 0

    def read(self, name, default):
        path = self.directory / (name + ".json")
        if not path.exists():
            return copy.deepcopy(default)
        # Never replace corrupted data silently with an empty list.
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def write(self, name, value):
        atomic_json(self.directory / (name + ".json"), value)

    def settings(self):
        with self.lock:
            result = copy.deepcopy(DEFAULT_SETTINGS)
            saved = self.read("settings", {})
            for channel, fields in result.items():
                fields.update({k: v for k, v in saved.get(channel, {}).items() if k in fields})
            return result

    def browser_event(self, reminder, trigger):
        with self.lock:
            self.sequence += 1
            self.events.append({"seq": self.sequence, "id": reminder["id"],
                                "content": reminder["content"], "time": trigger})
            self.events = self.events[-100:]


def public_settings(store):
    result = store.settings()
    result["email"]["auth_code_configured"] = bool(result["email"].pop("auth_code", ""))
    result["wecom"]["webhook_configured"] = bool(result["wecom"].pop("webhook", ""))
    return result


def valid_wecom_webhook(url):
    return isinstance(url, str) and bool(re.fullmatch(
        r"https://qyapi\.weixin\.qq\.com/cgi-bin/webhook/send\?key=[A-Za-z0-9_-]+", url))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def send_wecom(content, settings):
    webhook = settings["wecom"].get("webhook", "")
    if not webhook:
        return False, "未配置企业微信机器人 Webhook"
    if not valid_wecom_webhook(webhook):
        return False, "企业微信 Webhook 地址不正确，请重新复制机器人的地址"
    payload = json.dumps({"msgtype": "text", "text": {"content": content}}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(webhook, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
        code = result.get("errcode")
        if type(code) is int and code == 0:
            return True, ""
        # Do not expose errmsg or exceptions: they can contain the webhook key.
        message = "企业微信发送失败，请检查机器人是否有效"
        if type(code) is int:
            message += "（错误码 %s）" % code
        return False, message
    except Exception:
        return False, "企业微信发送失败，请检查 Webhook 地址及服务器网络"


def send_email(content, settings):
    cfg = settings["email"]
    if not all(cfg.get(k) for k in ("account", "auth_code", "to")):
        return False, "邮箱配置不完整"
    message = EmailMessage()
    message.set_content(content)
    message["From"], message["To"] = cfg["account"], cfg["to"]
    message["Subject"] = "⏰ 提醒通知"
    try:
        with smtplib.SMTP_SSL(cfg["smtp_host"], cfg["smtp_port"], timeout=15,
                              context=ssl.create_default_context()) as smtp:
            smtp.login(cfg["account"], cfg["auth_code"])
            smtp.send_message(message)
        return True, ""
    except smtplib.SMTPAuthenticationError:
        return False, "邮箱认证失败，请检查账号和 SMTP 授权码"
    except Exception:
        # SMTP responses can contain credentials or personal information.
        return False, "邮件发送失败，请检查 SMTP 地址、SSL 端口和网络"


def fire_reminder(store, reminder, trigger):
    results = {}
    for channel in reminder.get("channels", []):
        if channel == "browser":
            store.browser_event(reminder, trigger)
            results[channel] = {"ok": True, "message": ""}
        elif channel in ("email", "wecom"):
            sender = send_email if channel == "email" else send_wecom
            ok, message = sender("【%s】%s" % (trigger, reminder["content"]), store.settings())
            results[channel] = {"ok": ok, "message": message}
    return results


def matches(rule, now):
    kind = rule.get("type")
    return (kind == "daily" or (kind == "once" and rule.get("date") == now.strftime("%Y-%m-%d"))
            or (kind == "weekdays" and now.weekday() < 5)
            or (kind == "weekly" and now.weekday() in rule.get("days", [])))


def scheduler_tick(store, now=None):
    now = now or datetime.now(ZONE)
    key = now.strftime("%Y-%m-%d %H:%M")
    due = []
    with store.lock:
        reminders = store.read("reminders", [])
        for item in reminders:
            if (item.get("enabled", True) and item.get("time") == now.strftime("%H:%M")
                    and item.get("last_fired") != key and matches(item.get("rule", {}), now)):
                item["last_fired"] = key
                due.append(copy.deepcopy(item))
        if due:
            store.write("reminders", reminders)
    # Network operations and browser queue locks happen AFTER releasing the data lock.
    for item in due:
        results = fire_reminder(store, item, key)
        logging.info("Reminder %s: %s", item["id"],
                     {channel: value["ok"] for channel, value in results.items()})
    return len(due)


def scheduler_loop(store):
    while True:
        try:
            scheduler_tick(store)
        except Exception:
            logging.exception("Scheduler failed; data was not reset")
        time.sleep(5)


def validate_reminder(item):
    if not isinstance(item.get("content"), str) or not 1 <= len(item["content"].strip()) <= 2000:
        abort(400, "提醒内容需要 1–2000 个字符")
    item["content"] = item["content"].strip()
    if not isinstance(item.get("time"), str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", item["time"]):
        abort(400, "提醒时间格式不正确")
    rule = item.get("rule")
    if not isinstance(rule, dict) or rule.get("type") not in ("once", "daily", "weekdays", "weekly"):
        abort(400, "重复规则不正确")
    if rule["type"] == "once":
        try:
            if datetime.strptime(rule["date"], "%Y-%m-%d").strftime("%Y-%m-%d") != rule["date"]:
                raise ValueError()
        except (KeyError, ValueError, TypeError):
            abort(400, "日期不正确")
    if rule["type"] == "weekly":
        days = rule.get("days")
        if not isinstance(days, list) or not days or not all(type(d) is int and 0 <= d <= 6 for d in days):
            abort(400, "请选择有效的星期")
    channels = item.get("channels")
    if not isinstance(channels, list) or not channels or not all(c in ("browser", "email", "wecom") for c in channels):
        abort(400, "请选择邮件、企业微信或浏览器通知")
    item["channels"] = list(dict.fromkeys(channels))
    if type(item.get("enabled")) is not bool:
        abort(400, "启用状态不正确")


def create_app(config=None):
    app = Flask(__name__, static_folder=None)
    app.config.update(SECRET_KEY=os.environ.get("REMINDER_SECRET_KEY"),
                      PASSWORD_HASH=os.environ.get("REMINDER_PASSWORD_HASH"),
                      AUTH_FILE=os.environ.get("REMINDER_AUTH_FILE", str(BASE / "auth.json")), AUTH_VERSION=0,
                      DATA_DIR=os.environ.get("REMINDER_DATA_DIR", str(BASE / "data")),
                      SESSION_COOKIE_NAME="reminder_session", SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE="Strict", SESSION_COOKIE_SECURE=True,
                      PERMANENT_SESSION_LIFETIME=timedelta(days=30),
                      SESSION_REFRESH_EACH_REQUEST=True, MAX_CONTENT_LENGTH=16384)
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("REMINDER_LOCAL_HTTP") != "1"
    if config:
        app.config.update(config)
    auth_path = Path(app.config["AUTH_FILE"])
    if auth_path.exists():
        auth = json.loads(auth_path.read_text(encoding="utf-8"))
        app.config.update(SECRET_KEY=auth["secret_key"], PASSWORD_HASH=auth["password_hash"],
                          AUTH_VERSION=auth.get("auth_version", 0))
    if not app.config["SECRET_KEY"] or not app.config["PASSWORD_HASH"]:
        raise RuntimeError("请先运行 python setup_auth.py 设置登录密码")
    store = Store(app.config["DATA_DIR"])
    app.extensions["store"] = store
    attempts = []
    login_lock = threading.Lock()

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    @app.errorhandler(Exception)
    def server_error(error):
        logging.exception("Request failed")
        return jsonify(error="服务暂时异常，请查看服务器日志"), 500

    @app.after_request
    def response_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.before_request
    def protect_api():
        if request.path.startswith("/api/"):
            if session.get("owner") and session.get("auth_version", 0) != app.config["AUTH_VERSION"]:
                session.clear()
            if request.path not in ("/api/session", "/api/login") and not session.get("owner"):
                abort(401, "请先登录")
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                expected = session.get("csrf", "")
                supplied = request.headers.get("X-CSRF-Token", "")
                if not expected or not secrets.compare_digest(expected, supplied):
                    abort(403, "登录状态已变化，请刷新页面重试")

    def body():
        value = request.get_json()
        if not isinstance(value, dict):
            abort(400, "请求必须是 JSON 对象")
        return value

    @app.get("/")
    def index():
        return send_file(BASE / "index.html")

    @app.get("/api/session")
    def session_info():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        return jsonify(authenticated=bool(session.get("owner")), csrf=session["csrf"])

    @app.post("/api/login")
    def login():
        password = body().get("password", "")
        if not isinstance(password, str):
            abort(400, "密码格式不正确")
        # Single-owner global throttle cannot be bypassed with spoofed proxy headers.
        with login_lock:
            now = time.monotonic()
            attempts[:] = [stamp for stamp in attempts if now - stamp < 900]
            if len(attempts) >= 10:
                abort(429, "尝试次数过多，请 15 分钟后重试")
            if not check_password_hash(app.config["PASSWORD_HASH"], password):
                attempts.append(now)
                abort(401, "密码不正确")
            attempts.clear()
        session.clear()
        session.update(owner=True, csrf=secrets.token_urlsafe(32), auth_version=app.config["AUTH_VERSION"])
        session.permanent = True
        return jsonify(ok=True, csrf=session["csrf"])

    @app.post("/api/logout")
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.post("/api/password")
    def change_password():
        data = body()
        current = data.get("current_password")
        new = data.get("new_password")
        confirmation = data.get("confirm_password")
        if not isinstance(current, str) or not isinstance(new, str) or new == "":
            abort(400, "请填写当前密码和新密码")
        if new != confirmation:
            abort(400, "两次输入的新密码不一致")
        with login_lock:
            now = time.monotonic()
            attempts[:] = [stamp for stamp in attempts if now - stamp < 900]
            if len(attempts) >= 10:
                abort(429, "尝试次数过多，请 15 分钟后重试")
            if not check_password_hash(app.config["PASSWORD_HASH"], current):
                attempts.append(now)
                abort(400, "当前密码不正确")
            revised = {"secret_key": app.config["SECRET_KEY"], "password_hash": generate_password_hash(new),
                       "auth_version": secrets.token_hex(16)}
            # Persist before switching the live configuration so failures preserve the old password.
            atomic_json(auth_path, revised)
            app.config.update(PASSWORD_HASH=revised["password_hash"], AUTH_VERSION=revised["auth_version"])
            attempts.clear()
            session.clear()
        return jsonify(ok=True)

    @app.route("/api/reminders", methods=["GET", "POST"])
    def reminders():
        with store.lock:
            items = store.read("reminders", [])
            if request.method == "GET":
                return jsonify(items)
            data = body()
            item = {k: data.get(k) for k in ("content", "time", "rule", "channels")}
            item.update(id=uuid.uuid4().hex, enabled=True, last_fired=None,
                        created_at=datetime.now(ZONE).strftime("%Y-%m-%d %H:%M:%S"))
            validate_reminder(item)
            items.append(item)
            store.write("reminders", items)
            return jsonify(item), 201

    @app.route("/api/reminders/<rid>", methods=["PUT", "DELETE"])
    def reminder(rid):
        with store.lock:
            items = store.read("reminders", [])
            item = next((r for r in items if r["id"] == rid), None)
            if item is None:
                abort(404, "提醒不存在")
            if request.method == "DELETE":
                items.remove(item)
            else:
                data = body()
                item.update({k: data[k] for k in ("content", "time", "rule", "channels", "enabled") if k in data})
                validate_reminder(item)
                # Do not reset last_fired: editing in the same minute must not resend.
            store.write("reminders", items)
            return jsonify(ok=True) if request.method == "DELETE" else jsonify(item)

    @app.route("/api/settings", methods=["GET", "PUT"])
    def settings():
        if request.method == "PUT":
            data = body()
            if not data or not all(key in DEFAULT_SETTINGS and isinstance(fields, dict) for key, fields in data.items()):
                abort(400, "通知配置不正确")
            with store.lock:
                value = store.settings()
                for channel, incoming in data.items():
                    cfg = value[channel]
                    for key in cfg:
                        if key in incoming and not (key in ("auth_code", "webhook") and incoming[key] == ""):
                            cfg[key] = incoming[key]
                cfg = value["email"]
                for key in ("smtp_host", "account", "auth_code", "to"):
                    if not isinstance(cfg[key], str) or len(cfg[key]) > 512 or any(c in cfg[key] for c in "\r\n"):
                        abort(400, "邮箱配置格式不正确")
                if type(cfg["smtp_port"]) is not int or not 1 <= cfg["smtp_port"] <= 65535:
                    abort(400, "SMTP 端口不正确")
                webhook = value["wecom"]["webhook"]
                if not isinstance(webhook, str) or len(webhook) > 2048 or (webhook and not valid_wecom_webhook(webhook)):
                    abort(400, "企业微信 Webhook 地址不正确，请复制完整的机器人地址")
                store.write("settings", value)
        return jsonify(public_settings(store))

    @app.get("/api/poll")
    def poll():
        try:
            since = int(request.args.get("since", "0"))
        except ValueError:
            abort(400, "通知游标不正确")
        with store.lock:
            fresh = request.args.get("epoch") != store.epoch
            events = [] if fresh else [e for e in store.events if e["seq"] > since]
            return jsonify(cursor=store.sequence, epoch=store.epoch, events=events)

    @app.post("/api/test")
    def test_channel():
        channel = body().get("channel")
        if channel not in ("browser", "email", "wecom"):
            abort(400, "未知渠道")
        result = fire_reminder(store, {"id": "test", "content": "这是一条提醒测试", "channels": [channel]},
                               datetime.now(ZONE).strftime("%Y-%m-%d %H:%M"))
        return jsonify(result[channel])

    @app.post("/api/fire")
    def fire():
        rid = body().get("id")
        with store.lock:
            item = next((r for r in store.read("reminders", []) if r["id"] == rid), None)
        if item is None:
            abort(404, "提醒不存在")
        return jsonify(results=fire_reminder(store, item, datetime.now(ZONE).strftime("%Y-%m-%d %H:%M")))

    return app


if __name__ == "__main__":
    from waitress import serve
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    application = create_app()
    threading.Thread(target=scheduler_loop, args=(application.extensions["store"],), daemon=True).start()
    serve(application, host="127.0.0.1", port=int(os.environ.get("REMINDER_PORT", "8002")),
          threads=8, max_request_body_size=16384)
