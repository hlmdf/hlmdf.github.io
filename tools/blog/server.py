# -*- coding: utf-8 -*-
"""
【2026-11-09 新增】个人博客服务（文章 + 标签 + 照片 + 评论）

和片单、访客地图、飞机雷达同一配方：
- 纯 Python 标准库，不需要 pip install 任何东西
- 数据全部放数据目录（默认 ./data，服务器上 /var/lib/blog）：JSON 文件 + photos/ 目录
- 管理员密码首次启动时生成（也可用环境变量 BLOG_PASSWORD 指定），只存 PBKDF2 哈希；
  随机生成的初始密码写在数据目录的 initial-password.txt（权限 600）
- 登录后拿 HMAC 令牌（7 天有效），管理接口凭令牌访问；看文章、看照片、发评论不需要登录
- 服务器上用 deploy/install.sh 安装：Nginx 在 5012 提供 HTTPS，本进程只监听 127.0.0.1:8012

页面（同源，无需跨域）：
  GET /                 博客页面（列表、详情、后台都是这一个 HTML 里的前端路由）
  GET /photos/<文件名>  已上传的照片

公开接口：
  GET  /api/posts?tag=xx            文章列表（不含正文，按创建时间倒序）
  GET  /api/posts/<id>              单篇文章（含 Markdown 正文）
  GET  /api/tags                    标签及文章数
  GET  /api/posts/<id>/comments     某篇文章的评论
  POST /api/posts/<id>/comments     发表评论 {"name","content"}，按 IP 限流

管理接口（请求头 Authorization: Bearer <token>）：
  POST   /api/login                 {"password"} -> {"token"}
  POST   /api/posts                 新建文章 {"title","tags":[],"content"}
  PUT    /api/posts/<id>            修改文章
  DELETE /api/posts/<id>            删除文章（连带删它的评论）
  POST   /api/photos?name=xx.jpg    上传照片（请求体即文件内容，<=10MB）-> {"url"}
  GET    /api/comments              全部评论（管理用，倒序）
  DELETE /api/comments/<id>         删除评论
  POST   /api/password              改密码 {"current","next"}，改完全部令牌失效

本地试跑：
    python server.py --host 127.0.0.1 --port 8012

【2026-11-09 修改】按用户要求，接口错误提示全部中文化
（原英文提示：wrong password / 请先登录 / 没有找到 / rate limited /
try again later / bad request / empty or too large / only ... allowed）
"""

import argparse
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("BLOG_DATA_DIR", os.path.join(BASE, "data"))
PHOTOS_DIR = os.path.join(DATA_DIR, "photos")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
POSTS_PATH = os.path.join(DATA_DIR, "posts.json")
COMMENTS_PATH = os.path.join(DATA_DIR, "comments.json")
INDEX_PATH = os.path.join(BASE, "index.html")

TOKEN_TTL_SECONDS = 7 * 86400  # 登录令牌 7 天有效
MAX_JSON_BODY = 1 << 20  # JSON 请求体上限 1MB
MAX_PHOTO_BODY = 10 << 20  # 照片上限 10MB
PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"}

TITLE_MAX = 120
TAG_MAX = 24
TAGS_MAX = 10
CONTENT_MAX = 200_000
COMMENT_NAME_MAX = 20
COMMENT_MAX = 1000
COMMENT_URL_MAX = 3  # 评论里最多允许几个链接，挡垃圾广告

API_RATE_PER_MINUTE = 60  # 每个 IP 每分钟接口调用上限
LOGIN_RATE_PER_MINUTE = 10  # 登录尝试单独限流，防暴力猜密码
COMMENT_RATE_PER_HOUR = 10  # 每个 IP 每小时评论上限

data_lock = threading.Lock()
rate_lock = threading.Lock()
rate_table = {}  # key: (用途, ip) -> [窗口起点, 次数]


def ensure_dirs():
    os.makedirs(PHOTOS_DIR, exist_ok=True)


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, data):
    """原子写入：先写临时文件再替换，避免断电留下半个 JSON"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("ascii"), 120_000
    ).hex()
    return "%s$%s" % (salt, digest)


def check_password(password, stored):
    try:
        salt = stored.split("$", 1)[0]
    except (AttributeError, IndexError):
        return False
    return hmac.compare_digest(hash_password(password, salt), stored)


def make_token(secret):
    exp = int(time.time()) + TOKEN_TTL_SECONDS
    nonce = secrets.token_hex(8)
    msg = "%d.%s" % (exp, nonce)
    sig = hmac.new(secret.encode("ascii"), msg.encode("ascii"), hashlib.sha256).hexdigest()
    return "%s.%s" % (msg, sig)


def verify_token(secret, token):
    try:
        exp_text, nonce, sig = token.split(".")
        msg = "%s.%s" % (exp_text, nonce)
        want = hmac.new(secret.encode("ascii"), msg.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(want, sig):
            return False
        return int(exp_text) > time.time()
    except (ValueError, AttributeError):
        return False


def load_config():
    """首次启动：生成管理员密码并只存哈希。

    环境变量 BLOG_PASSWORD 可指定初始密码；没指定就随机生成一个，
    写进 initial-password.txt（权限 600）并打印到日志，看完可以删掉该文件。
    """
    cfg = load_json(CONFIG_PATH, None)
    if isinstance(cfg, dict) and cfg.get("password_hash") and cfg.get("token_secret"):
        return cfg

    password = os.environ.get("BLOG_PASSWORD", "").strip()
    generated = not password
    if generated:
        password = secrets.token_urlsafe(9)
    cfg = {
        "password_hash": hash_password(password),
        "token_secret": secrets.token_hex(32),
    }
    ensure_dirs()
    save_json(CONFIG_PATH, cfg)
    os.chmod(CONFIG_PATH, 0o600)
    if generated:
        notice = os.path.join(DATA_DIR, "initial-password.txt")
        with open(notice, "w", encoding="utf-8") as f:
            f.write(password + "\n")
        os.chmod(notice, 0o600)
        print("初始管理密码：%s（也写在 %s，设置好后可删除该文件）" % (password, notice))
    return cfg


def rate_ok(scope, ip, limit, window):
    """滑动窗口限流：window 秒内同一 IP 同一用途超过 limit 次就拒绝"""
    now = time.time()
    key = (scope, ip)
    with rate_lock:
        entry = rate_table.get(key)
        if not entry or now - entry[0] >= window:
            rate_table[key] = [now, 1]
            return True
        entry[1] += 1
        # 顺手清掉太老的条目，避免表无限涨
        if len(rate_table) > 10000:
            for k in [k for k, v in rate_table.items() if now - v[0] >= window]:
                del rate_table[k]
        return entry[1] <= limit


def strip_markdown(text):
    """把 Markdown 粗略还原成纯文本，用于列表页摘要"""
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)  # 图片
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # 链接留文字
    text = re.sub(r"[#>*`_~-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def public_post(post, with_content):
    item = {
        "id": post["id"],
        "title": post["title"],
        "tags": post["tags"],
        "created": post["created"],
        "updated": post["updated"],
    }
    if with_content:
        item["content"] = post["content"]
    else:
        item["summary"] = strip_markdown(post["content"])[:140]
    return item


def load_posts():
    return load_json(POSTS_PATH, {"posts": []})["posts"]


def load_comments():
    return load_json(COMMENTS_PATH, {"comments": []})["comments"]


def find_post(posts, post_id):
    for post in posts:
        if post["id"] == post_id:
            return post
    return None


def valid_tags(tags):
    if not isinstance(tags, list) or len(tags) > TAGS_MAX:
        return None
    cleaned = []
    for tag in tags:
        tag = str(tag).strip()
        if tag and len(tag) <= TAG_MAX and tag not in cleaned:
            cleaned.append(tag)
    return cleaned


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "Blog/1.0"

    def log_message(self, fmt, *args):
        pass  # 不打印访问日志，避免刷屏

    # ---------- 基础工具 ----------

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, content_type, cache_seconds):
        try:
            with open(path, "rb") as f:
                body = f.read()
        except OSError:
            self._send_json({"error": "没有找到"}, 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=%d" % cache_seconds)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self, limit):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if length <= 0 or length > limit:
            return None
        return self.rfile.read(length)

    def _read_json(self):
        raw = self._read_body(MAX_JSON_BODY)
        if not raw:
            return None
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def _client_ip(self):
        # 只相信本机反代写上的地址，公网直连时忽略客户端自带的转发头
        peer = self.client_address[0]
        if peer in ("127.0.0.1", "::1"):
            for header in ("X-Real-IP", "X-Forwarded-For"):
                value = self.headers.get(header)
                if value:
                    return value.split(",")[0].strip()
        return peer

    def _is_admin(self):
        header = self.headers.get("Authorization") or ""
        if not header.startswith("Bearer "):
            return False
        return verify_token(config["token_secret"], header[7:].strip())

    def _api_gate(self):
        """接口通用入口检查：限流。返回 False 表示已回复，调用方直接 return"""
        if not rate_ok("api", self._client_ip(), API_RATE_PER_MINUTE, 60):
            self._send_json({"error": "操作太频繁了，歇一会儿"}, 429)
            return False
        return True

    # ---------- 页面和照片 ----------

    def _serve_page(self):
        self._send_file(INDEX_PATH, "text/html; charset=utf-8", 0)

    def _serve_photo(self, name):
        # 文件名白名单 + 落在照片目录内，防目录穿越
        if not re.fullmatch(r"[A-Za-z0-9._-]+", name) or ".." in name:
            self._send_json({"error": "没有找到"}, 404)
            return
        path = os.path.realpath(os.path.join(PHOTOS_DIR, name))
        if not path.startswith(os.path.realpath(PHOTOS_DIR) + os.sep):
            self._send_json({"error": "没有找到"}, 404)
            return
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        self._send_file(path, ctype, 604800)  # 照片 immutable，缓存 7 天

    # ---------- GET ----------

    def do_GET(self):
        path, _, query = self.path.partition("?")
        path = path.rstrip("/") or "/"

        if path == "/health":
            self._send_json({"ok": True})
            return

        if path == "/":
            self._serve_page()
            return

        if path.startswith("/photos/"):
            self._serve_photo(path[len("/photos/"):])
            return

        if not self._api_gate():
            return

        if path == "/api/posts":
            params = urllib.parse.parse_qs(query)
            tag = params.get("tag", [""])[0].strip()
            with data_lock:
                posts = load_posts()
            if tag:
                posts = [p for p in posts if tag in p["tags"]]
            posts = sorted(posts, key=lambda p: p["created"], reverse=True)
            self._send_json({"posts": [public_post(p, False) for p in posts]})
            return

        if path == "/api/tags":
            with data_lock:
                posts = load_posts()
            counts = {}
            for p in posts:
                for t in p["tags"]:
                    counts[t] = counts.get(t, 0) + 1
            tags = sorted(
                ({"name": k, "count": v} for k, v in counts.items()),
                key=lambda x: (-x["count"], x["name"]),
            )
            self._send_json({"tags": tags})
            return

        match = re.fullmatch(r"/api/posts/(p-[0-9a-f]+)", path)
        if match:
            with data_lock:
                post = find_post(load_posts(), match.group(1))
            if not post:
                self._send_json({"error": "没有找到"}, 404)
                return
            self._send_json({"post": public_post(post, True)})
            return

        match = re.fullmatch(r"/api/posts/(p-[0-9a-f]+)/comments", path)
        if match:
            post_id = match.group(1)
            with data_lock:
                comments = [c for c in load_comments() if c["post_id"] == post_id]
            comments.sort(key=lambda c: c["created"])
            self._send_json({"comments": comments})
            return

        if path == "/api/comments":
            if not self._is_admin():
                self._send_json({"error": "请先登录"}, 401)
                return
            with data_lock:
                comments = load_comments()
                posts = load_posts()
            titles = {p["id"]: p["title"] for p in posts}
            for c in comments:
                c["post_title"] = titles.get(c["post_id"], "（文章已删除）")
            comments.sort(key=lambda c: c["created"], reverse=True)
            self._send_json({"comments": comments})
            return

        self._send_json({"error": "没有找到"}, 404)

    # ---------- POST ----------

    def do_POST(self):
        path, _, _ = self.path.partition("?")
        path = path.rstrip("/") or "/"

        if not self._api_gate():
            return

        if path == "/api/login":
            ip = self._client_ip()
            if not rate_ok("login", ip, LOGIN_RATE_PER_MINUTE, 60):
                self._send_json({"error": "尝试太多次了，一分钟后再试"}, 429)
                return
            data = self._read_json()
            password = str((data or {}).get("password") or "")
            if not password or not check_password(password, config["password_hash"]):
                self._send_json({"error": "密码不对"}, 401)
                return
            self._send_json({"token": make_token(config["token_secret"])})
            return

        if path == "/api/photos":
            if not self._is_admin():
                self._send_json({"error": "请先登录"}, 401)
                return
            params = urllib.parse.parse_qs(self.path.partition("?")[2])
            name = params.get("name", [""])[0].strip().lower()
            ext = os.path.splitext(name)[1]
            if ext not in PHOTO_EXTS:
                self._send_json({"error": "只支持这些图片格式：%s" % "/".join(sorted(PHOTO_EXTS))}, 400)
                return
            body = self._read_body(MAX_PHOTO_BODY)
            if not body:
                self._send_json({"error": "文件为空或超过 10MB 上限"}, 400)
                return
            # 文件名由服务端生成，避免重名覆盖和奇怪字符
            fname = "%d-%s%s" % (int(time.time()), secrets.token_hex(4), ext)
            ensure_dirs()
            with open(os.path.join(PHOTOS_DIR, fname), "wb") as f:
                f.write(body)
            self._send_json({"url": "/photos/" + fname})
            return

        if path == "/api/posts":
            if not self._is_admin():
                self._send_json({"error": "请先登录"}, 401)
                return
            data = self._read_json()
            error, post = validate_post(data)
            if error:
                self._send_json({"error": error}, 400)
                return
            post["id"] = "p-" + secrets.token_hex(6)
            post["created"] = int(time.time())
            post["updated"] = post["created"]
            with data_lock:
                posts = load_posts()
                posts.append(post)
                save_json(POSTS_PATH, {"posts": posts})
            self._send_json({"post": public_post(post, True)})
            return

        match = re.fullmatch(r"/api/posts/(p-[0-9a-f]+)/comments", path)
        if match:
            post_id = match.group(1)
            ip = self._client_ip()
            if not rate_ok("comment", ip, COMMENT_RATE_PER_HOUR, 3600):
                self._send_json({"error": "评论太频繁了，歇一会儿再发"}, 429)
                return
            data = self._read_json()
            error, comment = validate_comment(data)
            if error:
                self._send_json({"error": error}, 400)
                return
            with data_lock:
                if not find_post(load_posts(), post_id):
                    self._send_json({"error": "没有找到"}, 404)
                    return
                comment["id"] = "c-" + secrets.token_hex(6)
                comment["post_id"] = post_id
                comment["created"] = int(time.time())
                comments = load_comments()
                comments.append(comment)
                save_json(COMMENTS_PATH, {"comments": comments})
            self._send_json({"comment": comment})
            return

        if path == "/api/password":
            if not self._is_admin():
                self._send_json({"error": "请先登录"}, 401)
                return
            data = self._read_json()
            current = str((data or {}).get("current") or "")
            new = str((data or {}).get("next") or "")
            if not check_password(current, config["password_hash"]):
                self._send_json({"error": "当前密码不对"}, 403)
                return
            # 【2026-11-09 修改】按用户要求取消"新密码至少 8 位"限制，原代码：
            # if len(new) < 8:
            #     self._send_json({"error": "新密码至少 8 位"}, 400)
            #     return
            if not new:
                self._send_json({"error": "新密码不能为空"}, 400)
                return
            with data_lock:
                config["password_hash"] = hash_password(new)
                config["token_secret"] = secrets.token_hex(32)  # 旧令牌全部失效
                save_json(CONFIG_PATH, config)
                os.chmod(CONFIG_PATH, 0o600)
            self._send_json({"ok": True})
            return

        self._send_json({"error": "没有找到"}, 404)

    # ---------- PUT / DELETE ----------

    def do_PUT(self):
        path = self.path.partition("?")[0].rstrip("/") or "/"
        if not self._api_gate():
            return
        match = re.fullmatch(r"/api/posts/(p-[0-9a-f]+)", path)
        if not match:
            self._send_json({"error": "没有找到"}, 404)
            return
        if not self._is_admin():
            self._send_json({"error": "请先登录"}, 401)
            return
        data = self._read_json()
        error, fields = validate_post(data)
        if error:
            self._send_json({"error": error}, 400)
            return
        with data_lock:
            posts = load_posts()
            post = find_post(posts, match.group(1))
            if not post:
                self._send_json({"error": "没有找到"}, 404)
                return
            post.update(fields)
            post["updated"] = int(time.time())
            save_json(POSTS_PATH, {"posts": posts})
        self._send_json({"post": public_post(post, True)})

    def do_DELETE(self):
        path = self.path.partition("?")[0].rstrip("/") or "/"
        if not self._api_gate():
            return
        if not self._is_admin():
            self._send_json({"error": "请先登录"}, 401)
            return

        match = re.fullmatch(r"/api/posts/(p-[0-9a-f]+)", path)
        if match:
            post_id = match.group(1)
            with data_lock:
                posts = load_posts()
                kept = [p for p in posts if p["id"] != post_id]
                if len(kept) == len(posts):
                    self._send_json({"error": "没有找到"}, 404)
                    return
                save_json(POSTS_PATH, {"posts": kept})
                comments = [c for c in load_comments() if c["post_id"] != post_id]
                save_json(COMMENTS_PATH, {"comments": comments})
            self._send_json({"ok": True})
            return

        match = re.fullmatch(r"/api/comments/(c-[0-9a-f]+)", path)
        if match:
            comment_id = match.group(1)
            with data_lock:
                comments = load_comments()
                kept = [c for c in comments if c["id"] != comment_id]
                if len(kept) == len(comments):
                    self._send_json({"error": "没有找到"}, 404)
                    return
                save_json(COMMENTS_PATH, {"comments": kept})
            self._send_json({"ok": True})
            return

        self._send_json({"error": "没有找到"}, 404)


def validate_post(data):
    """校验文章字段，返回 (错误信息, 可用字段)；通过时错误信息为 None"""
    if not isinstance(data, dict):
        return "请求格式不对", None
    title = str(data.get("title") or "").strip()
    if not title or len(title) > TITLE_MAX:
        return "标题必填，且不超过 %d 字" % TITLE_MAX, None
    content = str(data.get("content") or "").strip()
    if not content or len(content) > CONTENT_MAX:
        return "正文必填", None
    tags = valid_tags(data.get("tags") or [])
    if tags is None:
        return "标签最多 %d 个" % TAGS_MAX, None
    return None, {"title": title, "content": content, "tags": tags}


def validate_comment(data):
    """校验评论字段，返回 (错误信息, 可用字段)

    防垃圾策略：昵称和内容必填、限制长度、限制链接数量。
    更狠的（验证码、审核后显示）对个人小站没必要，真被刷了再升级。
    """
    if not isinstance(data, dict):
        return "请求格式不对", None
    name = str(data.get("name") or "").strip()
    if not name or len(name) > COMMENT_NAME_MAX:
        return "昵称必填，且不超过 %d 字" % COMMENT_NAME_MAX, None
    content = str(data.get("content") or "").strip()
    if not content or len(content) > COMMENT_MAX:
        return "评论必填，且不超过 %d 字" % COMMENT_MAX, None
    if len(re.findall(r"https?://", content)) > COMMENT_URL_MAX:
        return "评论里链接太多了", None
    return None, {"name": name, "content": content}


config = {}


def main():
    global config
    parser = argparse.ArgumentParser(description="个人博客服务")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8012, help="监听端口")
    args = parser.parse_args()

    ensure_dirs()
    config = load_config()

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print("博客服务已启动：http://%s:%d" % (args.host, args.port))
    print("数据目录：%s" % DATA_DIR)
    print("按 Ctrl+C 停止。")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")


if __name__ == "__main__":
    main()
