#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
片单服务。只用 Python 3 标准库。

页面放在个人主页上，这个进程只负责：
  - 保存片单（movies.json）
  - 校验管理密码，访客只能看，不能改
  - 代为请求豆瓣搜索和封面

在阿里云上，和 /opt/bili-audio-tool、/opt/filedrop 一样：
  1. 文件放在 /opt/movie-tracker
  2. 本程序只监听 127.0.0.1:8001
  3. nginx 用已有证书在 8000 端口对外提供 https，再转发进来
  4. 第一次启动：
       MOVIE_PASSWORD='你的密码' python3 server.py 8001
  5. 忘记密码：停掉服务，删除 config.json，用新密码再启动一次。
     movies.json 里的片单还在。
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE, "config.json")
DATA_PATH = os.path.join(BASE, "movies.json")
LOCK = threading.Lock()
FAILS = {}
TOKEN_TTL = 30 * 24 * 3600
BLOCKED = {
    "config.json",
    "movies.json",
    "movies.json.bak",
    "movies.json.tmp",
    "cert.pem",
    "key.pem",
    "server.py",
}
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("ascii"), 120_000
    )
    return salt + "$" + digest.hex()


def check_password(password, stored):
    salt = stored.split("$", 1)[0]
    return hmac.compare_digest(hash_password(password, salt), stored)


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as handle:
            cfg = json.load(handle)
        if not cfg.get("password_hash") or not cfg.get("token_secret"):
            raise SystemExit("config.json 不完整。忘记密码的话，删掉它再重新设置。")
        return cfg

    password = os.environ.get("MOVIE_PASSWORD", "").strip()
    if len(password) < 6:
        raise SystemExit(
            "还没有管理密码。第一次请这样启动：\n"
            "  MOVIE_PASSWORD='至少6位的密码' python3 server.py 8000\n"
            "密码只会写成 config.json，之后不用再带这个环境变量。"
        )
    cfg = {
        "password_hash": hash_password(password),
        "token_secret": secrets.token_hex(32),
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as handle:
        json.dump(cfg, handle, indent=2)
        handle.write("\n")
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass
    print("已写入 config.json。之后直接 python3 server.py 8000 即可。")
    return cfg


def make_token(secret):
    exp = int(time.time()) + TOKEN_TTL
    nonce = secrets.token_hex(8)
    msg = "%d.%s" % (exp, nonce)
    sig = hmac.new(secret.encode("ascii"), msg.encode("ascii"), hashlib.sha256).hexdigest()
    return msg + "." + sig, exp


def verify_token(secret, token):
    try:
        exp_text, nonce, sig = token.split(".")
        exp = int(exp_text)
    except (ValueError, AttributeError):
        return False
    if exp < time.time() or not nonce:
        return False
    msg = "%s.%s" % (exp_text, nonce)
    expect = hmac.new(secret.encode("ascii"), msg.encode("ascii"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expect, sig)


def load_movies():
    if not os.path.exists(DATA_PATH):
        return []
    with open(DATA_PATH, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("movies.json 不是列表")
    return data


def save_movies(items):
    tmp = DATA_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(items, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    if os.path.exists(DATA_PATH):
        shutil.copy2(DATA_PATH, DATA_PATH + ".bak")
    os.replace(tmp, DATA_PATH)
    try:
        os.chmod(DATA_PATH, 0o600)
    except OSError:
        pass


def text_of(value, limit):
    if value is None:
        return ""
    return str(value).strip()[:limit]


def list_of(value, limit=20):
    if not value:
        return []
    if isinstance(value, str):
        value = re.split(r"[,，、/]", value)
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        piece = str(item).strip()[:40]
        if piece:
            out.append(piece)
        if len(out) >= limit:
            break
    return out


def clean_url(value):
    url = text_of(value, 500)
    if not url:
        return ""
    if not (url.startswith("https://") or url.startswith("http://")):
        raise ValueError("链接需要以 http:// 或 https:// 开头")
    return url


def clean_movie(body, movie_id):
    if not isinstance(body, dict):
        raise ValueError("格式不对")
    title = text_of(body.get("title"), 200)
    if not title:
        raise ValueError("请填写片名")
    year = body.get("year", "")
    if year in ("", None):
        year_out = ""
    else:
        try:
            year_out = int(year)
        except (TypeError, ValueError):
            raise ValueError("年份不对")
        if year_out < 1880 or year_out > 2100:
            raise ValueError("年份不对")
    rating = body.get("rating", "")
    if rating in ("", None):
        rating_out = ""
    else:
        try:
            rating_out = round(float(rating), 1)
        except (TypeError, ValueError):
            raise ValueError("评分不对")
        if rating_out < 0 or rating_out > 10:
            raise ValueError("评分要在 0 到 10 之间")
    kind = body.get("type")
    status = body.get("status")
    return {
        "id": movie_id,
        "title": title,
        "titleEn": text_of(body.get("titleEn"), 200),
        "year": year_out,
        "type": kind if kind in ("movie", "tv") else "movie",
        "status": status if status in ("watched", "want", "doing") else "watched",
        "director": text_of(body.get("director"), 200),
        "actors": list_of(body.get("actors")),
        "regions": list_of(body.get("regions")),
        "genres": list_of(body.get("genres")),
        "rating": rating_out,
        "douban": clean_url(body.get("douban")),
        "poster": clean_url(body.get("poster")),
    }


def new_id():
    return "m-" + secrets.token_hex(8)


SUBJECT_RE = re.compile(r"subject/(\d+)")


def fetch_douban(subject_id):
    """豆瓣搜索接口没有分数，添加时再查一次影片摘要。"""
    url = "https://movie.douban.com/j/subject_abstract?subject_id=" + urllib.parse.quote(subject_id)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://movie.douban.com/",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    subject = data.get("subject") if isinstance(data, dict) else None
    if not isinstance(subject, dict):
        return None
    rating = ""
    if subject.get("rate") not in ("", None):
        try:
            rating = round(float(subject.get("rate")), 1)
        except (TypeError, ValueError):
            rating = ""
        if rating != "" and (rating < 0 or rating > 10):
            rating = ""
    directors = subject.get("directors") if isinstance(subject.get("directors"), list) else []
    actors = subject.get("actors") if isinstance(subject.get("actors"), list) else []
    genres = subject.get("types") if isinstance(subject.get("types"), list) else []
    regions = [part for part in re.split(r"[\s/／、,，]+", str(subject.get("region") or "")) if part]
    year = ""
    if subject.get("release_year") not in ("", None):
        try:
            year = int(subject.get("release_year"))
        except (TypeError, ValueError):
            year = ""
    return {
        "rating": rating,
        "director": "，".join(str(name) for name in directors[:3] if name),
        "actors": [str(name) for name in actors[:8] if name],
        "genres": [str(name) for name in genres[:8] if name],
        "regions": regions[:8],
        "year": year,
    }


def enrich_movie(movie):
    match = SUBJECT_RE.search(movie.get("douban") or "")
    if not match:
        return movie
    needs = (
        movie.get("rating") in ("", None)
        or not movie.get("director")
        or not movie.get("actors")
        or not movie.get("genres")
        or not movie.get("regions")
    )
    if not needs:
        return movie
    info = fetch_douban(match.group(1))
    if not info:
        return movie
    if movie.get("rating") in ("", None) and info["rating"] != "":
        movie["rating"] = info["rating"]
    if not movie.get("director") and info["director"]:
        movie["director"] = info["director"]
    if not movie.get("actors") and info["actors"]:
        movie["actors"] = info["actors"]
    if not movie.get("genres") and info["genres"]:
        movie["genres"] = info["genres"]
    if not movie.get("regions") and info["regions"]:
        movie["regions"] = info["regions"]
    if movie.get("year") in ("", None) and info["year"] != "":
        movie["year"] = info["year"]
    return movie


def apply_missing(current, updated):
    """只补空着的字段，不覆盖已经填过的内容。"""
    changed = False
    if current.get("rating") in ("", None) and updated.get("rating") not in ("", None):
        current["rating"] = updated["rating"]
        changed = True
    if not current.get("director") and updated.get("director"):
        current["director"] = updated["director"]
        changed = True
    for key in ("actors", "genres", "regions"):
        if not current.get(key) and updated.get(key):
            current[key] = list(updated[key])
            changed = True
    if current.get("year") in ("", None) and updated.get("year") not in ("", None):
        current["year"] = updated["year"]
        changed = True
    return changed


DOUBAN_STATUS = {"done": "watched", "doing": "doing", "mark": "want"}
USER_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}$")


def parse_douban_user(text):
    text = text_of(text, 300)
    match = re.search(r"people/([^/?#\s]+)", text, re.I)
    uid = urllib.parse.unquote(match.group(1) if match else text).strip().strip("/")
    if not USER_RE.fullmatch(uid):
        return ""
    return uid


def person_names(value, limit):
    if not isinstance(value, list):
        return []
    names = []
    for item in value:
        name = item.get("name") if isinstance(item, dict) else item
        name = text_of(name, 40)
        if name:
            names.append(name)
        if len(names) >= limit:
            break
    return names


def regions_from_card(card):
    parts = [part.strip() for part in str(card or "").split("/")]
    if len(parts) < 2 or not parts[1]:
        return []
    return [part for part in re.split(r"\s+", parts[1]) if part][:8]


def subject_score(subject):
    rating = subject.get("rating")
    value = rating.get("value") if isinstance(rating, dict) else rating
    try:
        value = round(float(value), 1)
    except (TypeError, ValueError):
        return ""
    if value <= 0 or value > 10:
        return ""
    return value


def interest_to_movie(interest):
    if not isinstance(interest, dict):
        return None
    subject = interest.get("subject")
    if not isinstance(subject, dict):
        return None
    if subject.get("type") not in ("movie", "tv"):
        return None
    sid = str(subject.get("id") or "")
    if not sid.isdigit():
        return None
    year_text = str(subject.get("year") or "")
    year_match = re.search(r"(19|20)\d{2}", year_text)
    directors = person_names(subject.get("directors"), 3)
    try:
        return clean_movie({
            "title": subject.get("title") or "",
            "year": int(year_match.group(0)) if year_match else "",
            "type": subject.get("type"),
            "status": DOUBAN_STATUS.get(interest.get("status"), "watched"),
            "director": "，".join(directors),
            "actors": person_names(subject.get("actors"), 8),
            "regions": regions_from_card(subject.get("card_subtitle")),
            "genres": subject.get("genres") or [],
            "rating": subject_score(subject),
            "douban": subject.get("url") or ("https://movie.douban.com/subject/%s/" % sid),
            "poster": subject.get("cover_url") or "",
        }, new_id())
    except ValueError:
        return None


def fetch_douban_interests(uid, status, start):
    query = urllib.parse.urlencode({
        "status": status,
        "start": start,
        "count": 50,
        "for_mobile": 1,
    })
    url = "https://m.douban.com/rexxar/api/v2/user/%s/interests?%s" % (urllib.parse.quote(uid), query)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
        "Referer": "https://m.douban.com/people/%s/interests" % urllib.parse.quote(uid),
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ValueError("没有找到这个豆瓣用户")
        if exc.code in (401, 403):
            raise ValueError("这个片单没有公开。请在豆瓣把看过和想看设为所有人可见")
        raise ValueError("豆瓣暂时没有回应")
    except ValueError:
        raise
    except Exception:
        raise ValueError("豆瓣暂时没有回应")
    if not isinstance(data, dict) or not isinstance(data.get("interests"), list):
        raise ValueError("豆瓣返回的内容无法识别")
    return data["interests"]


def count_added(movies):
    counts = {
        "movie": {"watched": 0, "doing": 0, "want": 0},
        "tv": {"watched": 0, "doing": 0, "want": 0},
    }
    for movie in movies:
        kind = movie.get("type") if movie.get("type") in counts else "movie"
        status = movie.get("status") if movie.get("status") in counts[kind] else "watched"
        counts[kind][status] += 1
    return counts


def subject_id_of(movie):
    match = SUBJECT_RE.search(movie.get("douban") or "")
    return match.group(1) if match else ""


def client_ip_of(handler):
    return handler.client_address[0]


def login_locked(ip):
    rec = FAILS.get(ip)
    if not rec:
        return False
    if rec[1] and time.time() < rec[1]:
        return True
    if rec[1] and time.time() >= rec[1]:
        FAILS.pop(ip, None)
    return False


def note_login_failure(ip):
    count = FAILS.get(ip, [0, 0])[0] + 1
    lock_until = time.time() + 600 if count >= 8 else 0
    FAILS[ip] = [count, lock_until]


class Handler(SimpleHTTPRequestHandler):
    config = None

    def list_directory(self, path):
        self.send_error(404)
        return None

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        path = self.clean_path()
        if path.startswith("/api/"):
            return self.handle_api_get(path)
        if self.blocked(path):
            self.send_error(404)
            return
        super().do_GET()

    def do_POST(self):
        path = self.clean_path()
        if path == "/api/login":
            return self.handle_login()
        if path == "/api/movies/fill-ratings" or path == "/api/movies/refresh":
            return self.handle_refresh()
        if path == "/api/movies/import-douban":
            return self.handle_import_douban()
        if path == "/api/movies":
            return self.handle_create()
        self.send_json({"error": "没有这个接口"}, 404)

    def do_PUT(self):
        path = self.clean_path()
        if path == "/api/movies":
            return self.handle_import()
        if path.startswith("/api/movies/"):
            return self.handle_update(path.split("/", 3)[3])
        self.send_json({"error": "没有这个接口"}, 404)

    def do_DELETE(self):
        path = self.clean_path()
        if path.startswith("/api/movies/"):
            return self.handle_delete(path.split("/", 3)[3])
        self.send_json({"error": "没有这个接口"}, 404)

    def clean_path(self):
        path = urllib.parse.urlparse(self.path).path
        if len(path) > 1 and path.endswith("/"):
            path = path[:-1]
        return path

    def blocked(self, path):
        rel = urllib.parse.unquote(path).replace("\\", "/").lstrip("/")
        if ".." in rel.split("/"):
            return True
        return os.path.basename(rel) in BLOCKED

    def read_json(self, limit=1_000_000):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("请求不对")
        if length < 0 or length > limit:
            raise ValueError("内容太大")
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("内容不是 JSON")

    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return False
        return verify_token(self.config["token_secret"], header[7:].strip())

    def require_auth(self):
        if self.authorized():
            return True
        self.send_json({"error": "请先登录"}, 401)
        return False

    def handle_api_get(self, path):
        if path == "/api/movies":
            with LOCK:
                try:
                    items = load_movies()
                except ValueError as exc:
                    return self.send_json({"error": str(exc)}, 500)
            return self.send_json(items)
        if path == "/api/me":
            if not self.authorized():
                return self.send_json({"error": "请先登录"}, 401)
            return self.send_json({"ok": True})
        if path == "/api/health":
            return self.send_json({"ok": True})
        if path.startswith("/api/suggest"):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            return self.handle_suggest(query.get("q", [""])[0].strip())
        if path.startswith("/api/img"):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            return self.handle_img(query.get("url", [""])[0])
        self.send_json({"error": "没有这个接口"}, 404)

    def handle_login(self):
        ip = client_ip_of(self)
        if login_locked(ip):
            return self.send_json({"error": "试得太多了，请 10 分钟后再试"}, 429)
        try:
            body = self.read_json(10_000)
        except ValueError as exc:
            return self.send_json({"error": str(exc)}, 400)
        password = body.get("password") if isinstance(body, dict) else ""
        password = password if isinstance(password, str) else ""
        if not check_password(password, self.config["password_hash"]):
            note_login_failure(ip)
            time.sleep(0.4)
            return self.send_json({"error": "密码不对"}, 401)
        FAILS.pop(ip, None)
        token, exp = make_token(self.config["token_secret"])
        self.send_json({"token": token, "expires": exp})

    def handle_create(self):
        if not self.require_auth():
            return
        try:
            body = self.read_json()
            movie = clean_movie(body, new_id())
            movie = enrich_movie(movie)
        except ValueError as exc:
            return self.send_json({"error": str(exc)}, 400)
        with LOCK:
            try:
                items = load_movies()
            except ValueError as exc:
                return self.send_json({"error": str(exc)}, 500)
            if len(items) >= 5000:
                return self.send_json({"error": "片单已经太多了"}, 400)
            items.append(movie)
            save_movies(items)
        self.send_json({"ok": True, "item": movie, "items": items})

    def handle_update(self, movie_id):
        if not self.require_auth():
            return
        movie_id = urllib.parse.unquote(movie_id)
        try:
            body = self.read_json()
            movie = clean_movie(body, movie_id)
            movie = enrich_movie(movie)
        except ValueError as exc:
            return self.send_json({"error": str(exc)}, 400)
        with LOCK:
            try:
                items = load_movies()
            except ValueError as exc:
                return self.send_json({"error": str(exc)}, 500)
            for index, item in enumerate(items):
                if item.get("id") == movie_id:
                    items[index] = movie
                    save_movies(items)
                    return self.send_json({"ok": True, "item": movie, "items": items})
        self.send_json({"error": "没有这部片子"}, 404)

    def handle_delete(self, movie_id):
        if not self.require_auth():
            return
        movie_id = urllib.parse.unquote(movie_id)
        with LOCK:
            try:
                items = load_movies()
            except ValueError as exc:
                return self.send_json({"error": str(exc)}, 500)
            kept = [item for item in items if item.get("id") != movie_id]
            if len(kept) == len(items):
                return self.send_json({"error": "没有这部片子"}, 404)
            save_movies(kept)
        self.send_json({"ok": True, "items": kept})

    def handle_refresh(self):
        if not self.require_auth():
            return
        with LOCK:
            try:
                items = load_movies()
            except ValueError as exc:
                return self.send_json({"error": str(exc)}, 500)
        changed = 0
        attempts = 0
        more = False
        for movie in items:
            if not SUBJECT_RE.search(movie.get("douban") or ""):
                continue
            before = {
                "rating": movie.get("rating"),
                "director": movie.get("director"),
                "actors": list(movie.get("actors") or []),
                "genres": list(movie.get("genres") or []),
                "regions": list(movie.get("regions") or []),
                "year": movie.get("year"),
            }
            if not (
                before["rating"] in ("", None)
                or not before["director"]
                or not before["actors"]
                or not before["genres"]
                or not before["regions"]
                or before["year"] in ("", None)
            ):
                continue
            attempts += 1
            if attempts > 40:
                more = True
                break
            enrich_movie(movie)
            if apply_missing(before, movie):
                changed += 1
        if changed:
            with LOCK:
                try:
                    current = load_movies()
                except ValueError as exc:
                    return self.send_json({"error": str(exc)}, 500)
                filled = {movie.get("id"): movie for movie in items}
                for index, movie in enumerate(current):
                    updated = filled.get(movie.get("id"))
                    if updated and apply_missing(movie, updated):
                        current[index] = movie
                save_movies(current)
                items = current
        self.send_json({"ok": True, "filled": changed, "more": more, "items": items})

    def handle_import_douban(self):
        if not self.require_auth():
            return
        try:
            body = self.read_json()
        except ValueError as exc:
            return self.send_json({"error": str(exc)}, 400)
        if not isinstance(body, dict):
            return self.send_json({"error": "格式不对"}, 400)
        uid = parse_douban_user(body.get("user"))
        if not uid:
            return self.send_json({"error": "请填写豆瓣个人主页链接，或 people/ 后面的那段 ID"}, 400)
        wanted = body.get("statuses")
        if not isinstance(wanted, list) or not wanted:
            wanted = ["done", "doing", "mark"]
        statuses = [item for item in ("done", "doing", "mark") if item in wanted]
        if not statuses:
            return self.send_json({"error": "请至少选择看过、在看或想看中的一种"}, 400)
        raw_cursors = body.get("cursors") if isinstance(body.get("cursors"), dict) else {}
        with LOCK:
            try:
                current = load_movies()
            except ValueError as exc:
                return self.send_json({"error": str(exc)}, 500)
        seen = {sid for sid in (subject_id_of(movie) for movie in current) if sid}
        fresh = []
        skipped = 0
        more = False
        next_cursors = {}
        deadline = time.time() + 40
        try:
            for status in statuses:
                try:
                    start = max(0, int(raw_cursors.get(status) or 0))
                except (TypeError, ValueError):
                    start = 0
                finished = False
                while True:
                    if time.time() > deadline or len(fresh) >= 2000:
                        break
                    interests = fetch_douban_interests(uid, status, start)
                    if not interests:
                        finished = True
                        break
                    for interest in interests:
                        movie = interest_to_movie(interest)
                        if not movie:
                            continue
                        sid = subject_id_of(movie)
                        if not sid or sid in seen:
                            if sid in seen:
                                skipped += 1
                            continue
                        seen.add(sid)
                        fresh.append(movie)
                    if len(interests) < 50:
                        finished = True
                        break
                    start += 50
                    time.sleep(0.25)
                next_cursors[status] = 0 if finished else start
                if not finished:
                    more = True
                    break
        except ValueError as exc:
            return self.send_json({"error": str(exc)}, 502)
        for status in statuses:
            if status not in next_cursors:
                try:
                    next_cursors[status] = max(0, int(raw_cursors.get(status) or 0))
                except (TypeError, ValueError):
                    next_cursors[status] = 0
        inserted = []
        with LOCK:
            try:
                current = load_movies()
            except ValueError as exc:
                return self.send_json({"error": str(exc)}, 500)
            have = {sid for sid in (subject_id_of(movie) for movie in current) if sid}
            for movie in fresh:
                sid = subject_id_of(movie)
                if sid in have:
                    skipped += 1
                    continue
                have.add(sid)
                current.append(movie)
                inserted.append(movie)
            if inserted:
                save_movies(current)
        self.send_json({
            "ok": True,
            "added": len(inserted),
            "counts": count_added(inserted),
            "skipped": skipped,
            "more": more,
            "cursors": next_cursors,
            "items": current,
        })

    def handle_import(self):
        if not self.require_auth():
            return
        try:
            body = self.read_json(2_000_000)
        except ValueError as exc:
            return self.send_json({"error": str(exc)}, 400)
        if not isinstance(body, list):
            return self.send_json({"error": "导入的文件应该是一个列表"}, 400)
        if len(body) > 5000:
            return self.send_json({"error": "一次最多导入 5000 部"}, 400)
        items = []
        used = set()
        try:
            for raw in body:
                movie_id = raw.get("id") if isinstance(raw, dict) else ""
                if not isinstance(movie_id, str) or not ID_RE.match(movie_id) or movie_id in used:
                    movie_id = new_id()
                used.add(movie_id)
                items.append(clean_movie(raw, movie_id))
        except ValueError as exc:
            return self.send_json({"error": str(exc)}, 400)
        with LOCK:
            save_movies(items)
        self.send_json({"ok": True, "items": items})

    def handle_suggest(self, keyword):
        if not keyword:
            return self.send_json([])
        url = "https://movie.douban.com/j/subject_suggest?q=" + urllib.parse.quote(keyword)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception:
            return self.send_json([])
        if not isinstance(data, list):
            return self.send_json([])
        out = [{
            "title": item.get("title", ""),
            "year": item.get("year", ""),
            "img": item.get("img", ""),
            "url": item.get("url", ""),
            "episode": item.get("episode", ""),
        } for item in data if isinstance(item, dict)][:10]
        self.send_json(out)

    def handle_img(self, url):
        host = urllib.parse.urlparse(url).netloc.lower()
        allowed = (
            host == "doubanio.com" or host.endswith(".doubanio.com")
            or host == "douban.com" or host.endswith(".douban.com")
        )
        if not allowed:
            self.send_error(403)
            return
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": "https://movie.douban.com/",
        })
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                data = response.read()
                ctype = response.headers.get("Content-Type", "image/jpeg")
        except Exception:
            self.send_error(502)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype.split(";")[0] or "image/jpeg")
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    os.chdir(BASE)
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8001
    Handler.config = load_config()
    ThreadingHTTPServer.allow_reuse_address = True
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("片单服务已启动: http://127.0.0.1:%d （按 Ctrl+C 停止）" % port)
    print("对外地址由 nginx 的 8000 端口提供 https。")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
