#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
书单服务。只用 Python 3 标准库。

页面放在个人主页上，这个进程只负责：
  - 保存书单（books.json）
  - 校验管理密码，访客只能看，不能改
  - 代为请求豆瓣搜索和封面

在阿里云上，和 /opt/bili-audio-tool、/opt/filedrop 一样：
  1. 文件放在 /opt/book-tracker
  2. 本程序只监听 127.0.0.1:8001
  3. nginx 用已有证书在 8000 端口对外提供 https，再转发进来
  4. 第一次启动：
       BOOK_PASSWORD='你的密码' python3 server.py 8001
  5. 忘记密码：停掉服务，删除 config.json，用新密码再启动一次。
     books.json 里的书单还在。
"""
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import hmac
import html
import http.cookiejar
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
DATA_PATH = os.path.join(BASE, "books.json")
DOUBAN_SESSION_PATH = os.path.join(BASE, "douban_session.json")
DOUBAN_PENDING_PATH = os.path.join(BASE, "douban_pending.json")
LOCK = threading.Lock()
AUTH_LOCK = threading.RLock()
DOUBAN_LOCK = threading.Lock()
FAILS = {}
TOKEN_TTL = 30 * 24 * 3600
BLOCKED = {
    "config.json",
    "config.json.tmp",
    "books.json",
    "books.json.bak",
    "books.json.tmp",
    "cert.pem",
    "key.pem",
    "server.py",
    "douban_session.json",
    "douban_pending.json",
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

    password = os.environ.get("BOOK_PASSWORD", "")
    if not password:
        raise SystemExit(
            "还没有管理密码。第一次请这样启动：\n"
            "  BOOK_PASSWORD='你的管理密码' python3 server.py 8000\n"
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


def change_management_password(config, current, new, confirmation):
    """Change only the local book administrator password and invalidate its tokens."""
    if not isinstance(current, str) or not isinstance(new, str) or not new:
        raise ValueError("请填写当前管理密码和新密码")
    if new != confirmation:
        raise ValueError("两次输入的新密码不一致")
    if not check_password(current, config["password_hash"]):
        raise ValueError("当前管理密码不正确")
    revised = dict(config)
    revised.update(password_hash=hash_password(new), token_secret=secrets.token_hex(32))
    temporary = CONFIG_PATH + ".tmp"
    try:
        fd = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(revised, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, CONFIG_PATH)
        config.update(revised)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


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


def load_books():
    if not os.path.exists(DATA_PATH):
        return []
    with open(DATA_PATH, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("books.json 不是列表")
    return data


def save_books(items):
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


def larger_poster(value):
    """搜索列表给的是高度大约 120 的缩略图，换成豆瓣的中号海报。"""
    url = clean_url(value)
    if not url:
        return ""
    host = urllib.parse.urlparse(url).netloc.lower()
    if not (host.endswith("doubanio.com") or host.endswith("douban.com")):
        return url
    match = re.search(r"/(p\d+)\.(?:jpg|jpeg|webp|png)", urllib.parse.urlparse(url).path, re.I)
    if not match:
        return url
    return "https://img3.doubanio.com/view/photo/m_ratio_poster/public/%s.jpg" % match.group(1)


def clean_book(body, book_id):
    if not isinstance(body, dict):
        raise ValueError("格式不对")
    title = text_of(body.get("title"), 200)
    if not title:
        raise ValueError("请填写书名")
    year = body.get("year", "")
    if year in ("", None):
        year_out = ""
    else:
        try:
            year_out = int(year)
        except (TypeError, ValueError):
            raise ValueError("出版年份不对")
        if year_out < 1000 or year_out > 2100:
            raise ValueError("出版年份不对")
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
    status = body.get("status")
    review = clean_review(body)
    return {
        "id": book_id,
        "title": title,
        "titleEn": text_of(body.get("titleEn"), 200),
        "year": year_out,
        "status": status if status in ("read", "reading", "want") else "read",
        "author": text_of(body.get("author"), 200),
        "translator": list_of(body.get("translator")),
        "publishers": list_of(body.get("publishers")),
        "genres": list_of(body.get("genres")),
        "rating": rating_out,
        "douban": clean_url(body.get("douban")),
        "poster": larger_poster(body.get("poster")),
        **review,
    }

def clean_review(body):
    personal = body.get("personalRating", "")
    if personal in ("", None):
        personal = ""
    elif type(personal) not in (str, int) or str(personal) not in ("1", "2", "3", "4", "5"):
        raise ValueError("个人评分请选择 1–5 颗星，或不评分")
    else:
        personal = int(personal)
    tags = body.get("tags", [])
    if isinstance(tags, str):
        tags = tags.split()
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise ValueError("标签格式不正确")
    tags = list(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))
    comment = body.get("comment", "")
    if not isinstance(comment, str) or len(comment) > 350:
        raise ValueError("简短评论最多 350 字")
    private = body.get("doubanPrivate", False)
    if type(private) is not bool:
        raise ValueError("豆瓣可见性不正确")
    return {"personalRating": personal, "tags": tags, "comment": comment, "doubanPrivate": private}


def new_id():
    return "b-" + secrets.token_hex(8)


SUBJECT_RE = re.compile(r"subject/(\d+)")


def people_line(text):
    return " / ".join(part for part in re.split(r"\s+", str(text or "").strip()) if part)


def parse_card_subtitle(text):
    """豆瓣读书的副标题一般是：作者 / 出版年 / 出版社；有译者时作者后面多一段。

    国籍会被豆瓣单独放在一段（"[哥伦比亚] / 加西亚·马尔克斯 / 2011 / 南海"），
    先把它粘回作者名，否则国籍会被当成作者、作者被当成译者。
    """
    parts = [part.strip() for part in re.split(r"\s*/\s*", str(text or "")) if part.strip()]
    merged = []
    for part in parts:
        if merged and re.fullmatch(r"\[[^\]]*\]", merged[-1]):
            merged[-1] = merged[-1] + " " + part
        else:
            merged.append(part)
    parts = merged

    year_index = -1
    for index, part in enumerate(parts):
        if re.fullmatch(r"(?:19|20)\d{2}", part):
            year_index = index
            break
    if year_index < 0:
        return {
            "author": parts[0] if parts else "",
            "translator": "",
            "publisher": parts[-1] if len(parts) > 1 else "",
            "year": "",
        }
    return {
        # 作者名里的空格是姓名的一部分（"[哥伦比亚] 加西亚·马尔克斯"），
        # 不能像电影导演那样用 people_line 拆成斜杠分隔。
        "author": parts[0] if year_index >= 1 else "",
        "translator": parts[1] if year_index >= 2 else "",
        "publisher": parts[year_index + 1] if len(parts) > year_index + 1 else "",
        "year": parts[year_index],
    }

def fetch_search_intro(kind, sid):
    """豆瓣读书简介。电影版要在 movie/tv 两条路径间试，书只有 book 一条。"""
    url = "https://m.douban.com/rexxar/api/v2/book/%s" % sid
    req = urllib.request.Request(url, headers={
        "User-Agent": DOUBAN_UA,
        "Referer": "https://m.douban.com/search/",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=6) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    intro = re.sub(r"\s+", " ", str(data.get("intro") or "")).strip()
    return intro[:2000]


def suggest_douban(keyword, start=0):
    """豆瓣读书搜索。结果自带评分和简介，不必再逐条查详情。"""
    url = "https://m.douban.com/rexxar/api/v2/search/book?q=%s&count=10&start=%d" % (
        urllib.parse.quote(keyword), start)
    req = urllib.request.Request(url, headers={
        "User-Agent": DOUBAN_UA,
        "Referer": "https://m.douban.com/search/",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=10) as response:
        data = json.loads(response.read().decode("utf-8"))
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError("豆瓣搜索没有结果")
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        target = item.get("target") if isinstance(item.get("target"), dict) else {}
        kind = str(item.get("target_type") or "")
        sid = str(target.get("id") or "")
        if kind != "book" or not sid.isdigit():
            continue
        extra = parse_card_subtitle(target.get("card_subtitle"))
        out.append({
            "title": target.get("title") or "",
            "year": extra["year"],
            "img": target.get("cover_url") or "",
            "url": "https://book.douban.com/subject/%s/" % sid,
            "author": extra["author"],
            "translator": extra["translator"],
            "publishers": [extra["publisher"]] if extra["publisher"] else [],
            "genres": [],
            "rating": subject_score(target),
            "intro": re.sub(r"\s+", " ", str(target.get("abstract") or "")).strip()[:400],
        })
    next_start = start + len(items)
    total = data.get("total")
    has_more = bool(items) and (next_start < total if isinstance(total, int) else len(items) >= 10)
    return {"results": out, "nextStart": next_start, "hasMore": has_more}

def fetch_book(subject_id):
    """豆瓣读书详情，用来补评分、出版社和出版年。"""
    url = "https://m.douban.com/rexxar/api/v2/book/" + urllib.parse.quote(subject_id)
    req = urllib.request.Request(url, headers={
        "User-Agent": DOUBAN_UA,
        "Referer": "https://m.douban.com/",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    pubdate = data.get("pubdate")
    if isinstance(pubdate, list):
        pubdate = pubdate[0] if pubdate else ""
    match = re.search(r"(19|20)\d{2}", str(pubdate or ""))
    press = data.get("press")
    if isinstance(press, list):
        press_out = [str(item) for item in press[:4] if item]
    else:
        press_out = [str(press)] if press else []
    translators = data.get("translator")
    translators = translators if isinstance(translators, list) else []
    return {
        "rating": subject_score(data),
        "author": "，".join(person_names(data.get("author"), 3)),
        "translator": [str(item) for item in translators[:8] if item],
        "publishers": press_out,
        "year": int(match.group(0)) if match else "",
        "intro": re.sub(r"\s+", " ", str(data.get("intro") or "")).strip(),
        # 豆瓣读书没有电影那样的类型字段，详情里的 tags 是唯一的分类来源，
        # 而且只有带登录态时才偶尔给值，所以拿不到就留空。
        "genres": [
            str(tag.get("name")) for tag in (data.get("tags") or [])[:6]
            if isinstance(tag, dict) and tag.get("name")
        ],
    }

def enrich_book(book):
    match = SUBJECT_RE.search(book.get("douban") or "")
    if not match:
        return book
    needs = (
        book.get("rating") in ("", None)
        or not book.get("author")
        or not book.get("publishers")
        or book.get("year") in ("", None)
    )
    if not needs:
        return book
    info = fetch_book(match.group(1))
    if not info:
        return book
    if book.get("rating") in ("", None) and info["rating"] != "":
        book["rating"] = info["rating"]
    if not book.get("author") and info["author"]:
        book["author"] = info["author"]
    if not book.get("translator") and info["translator"]:
        book["translator"] = info["translator"]
    if not book.get("publishers") and info["publishers"]:
        book["publishers"] = info["publishers"]
    if not book.get("genres") and info.get("genres"):
        book["genres"] = info["genres"]
    if book.get("year") in ("", None) and info["year"] != "":
        book["year"] = info["year"]
    return book

def apply_missing(current, updated):
    """只补空着的字段，不覆盖已经填过的内容。"""
    changed = False
    if current.get("rating") in ("", None) and updated.get("rating") not in ("", None):
        current["rating"] = updated["rating"]
        changed = True
    if not current.get("author") and updated.get("author"):
        current["author"] = updated["author"]
        changed = True
    for key in ("translator", "genres", "publishers"):
        if not current.get(key) and updated.get(key):
            current[key] = list(updated[key])
            changed = True
    if current.get("year") in ("", None) and updated.get("year") not in ("", None):
        current["year"] = updated["year"]
        changed = True
    return changed


DOUBAN_STATUS = {"done": "read", "reading": "reading", "mark": "want"}
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


def publishers_from_card(card):
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


def interest_to_book(interest):
    if not isinstance(interest, dict):
        return None
    subject = interest.get("subject")
    if not isinstance(subject, dict):
        return None
    if subject.get("type") != "book":
        return None
    sid = str(subject.get("id") or "")
    if not sid.isdigit():
        return None
    year_text = str(subject.get("year") or "")
    year_match = re.search(r"(19|20)\d{2}", year_text)
    authors = person_names(subject.get("authors"), 3)
    try:
        return clean_book({
            "title": subject.get("title") or "",
            "year": int(year_match.group(0)) if year_match else "",
            "status": DOUBAN_STATUS.get(interest.get("status"), "read"),
            "author": "，".join(authors),
            "translator": person_names(subject.get("translator"), 8),
            "publishers": publishers_from_card(subject.get("card_subtitle")),
            "genres": subject.get("genres") or [],
            "rating": subject_score(subject),
            "douban": subject.get("url") or ("https://book.douban.com/subject/%s/" % sid),
            "poster": subject.get("cover_url") or "",
        }, new_id())
    except ValueError:
        return None


DOUBAN_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
DOUBAN_GRID_PAGE = 15
COLLECT_KIND = {"done": "collect", "reading": "do", "mark": "wish"}
PAGE_STATUS_TO_DOUBAN = {"read": "collect", "reading": "do", "want": "wish"}


class DoubanNoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def douban_cookie(name, value):
    return http.cookiejar.Cookie(
        0, str(name), str(value),
        None, False,
        ".douban.com", True, True,
        "/", True,
        False, None, True,
        None, None, {},
    )


def opener_from_cookies(cookies, follow_redirect=True):
    jar = http.cookiejar.CookieJar()
    for name, value in (cookies or {}).items():
        if name and value is not None:
            jar.set_cookie(douban_cookie(name, value))
    handlers = [urllib.request.HTTPCookieProcessor(jar)]
    if not follow_redirect:
        handlers.insert(0, DoubanNoRedirect())
    return urllib.request.build_opener(*handlers), jar


def jar_dict(jar):
    return {cookie.name: cookie.value for cookie in jar}


def uid_from_cookies(cookies):
    raw = str((cookies or {}).get("dbcl2") or "").strip().strip('"')
    match = re.match(r"(\d+):", raw)
    return match.group(1) if match else ""


def load_douban_session():
    if not os.path.exists(DOUBAN_SESSION_PATH):
        return None
    try:
        with open(DOUBAN_SESSION_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    cookies = data.get("cookies") if isinstance(data, dict) else None
    uid = uid_from_cookies(cookies)
    if not uid or not isinstance(cookies, dict):
        return None
    return {"uid": uid, "cookies": cookies}


def save_douban_session(cookies):
    uid = uid_from_cookies(cookies)
    if not uid:
        raise ValueError("豆瓣没有登录成功")
    payload = {"uid": uid, "cookies": cookies, "saved_at": int(time.time())}
    tmp = DOUBAN_SESSION_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    os.chmod(tmp, 0o600)
    os.replace(tmp, DOUBAN_SESSION_PATH)
    try:
        os.chmod(DOUBAN_SESSION_PATH, 0o600)
    except OSError:
        pass
    return uid


def clear_douban_session():
    if os.path.exists(DOUBAN_SESSION_PATH):
        os.remove(DOUBAN_SESSION_PATH)


def write_secret_json(path, payload):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_pending_cookies():
    if not os.path.exists(DOUBAN_PENDING_PATH):
        return {}
    try:
        with open(DOUBAN_PENDING_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    try:
        saved_at = int(data.get("saved_at") or 0)
    except (TypeError, ValueError):
        saved_at = 0
    if int(time.time()) - saved_at > 1800:
        return {}
    cookies = data.get("cookies")
    if not isinstance(cookies, dict):
        return {}
    clean = {}
    for name, value in cookies.items():
        if isinstance(name, str) and isinstance(value, str) and 0 < len(name) <= 64 and len(value) <= 4000:
            clean[name] = value
    return clean


def save_pending_cookies(cookies):
    write_secret_json(DOUBAN_PENDING_PATH, {"cookies": cookies, "saved_at": int(time.time())})


def clear_pending_cookies():
    if os.path.exists(DOUBAN_PENDING_PATH):
        os.remove(DOUBAN_PENDING_PATH)


TOUCH_CAP_RE = re.compile(r"^https://([\w-]+\.)+(qq|tencent|qcloud)\.com(/|$)")
PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
AREA_RE = re.compile(r"^\+\d{1,4}$")


def douban_form_headers():
    return {
        "User-Agent": DOUBAN_UA,
        "Origin": "https://accounts.douban.com",
        "Referer": "https://accounts.douban.com/passport/login",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    }


def begin_douban_opener():
    with DOUBAN_LOCK:
        cookies = load_pending_cookies()
    opener, jar = opener_from_cookies(cookies)
    if not jar_dict(jar).get("bid"):
        try:
            opener.open(urllib.request.Request(
                "https://accounts.douban.com/passport/login",
                headers={"User-Agent": DOUBAN_UA},
            ), timeout=15).read()
        except Exception:
            pass
    return opener, jar


def douban_post(path, fields):
    opener, jar = begin_douban_opener()
    body = {"ck": jar_dict(jar).get("ck") or ""}
    body.update(fields)
    req = urllib.request.Request(
        "https://accounts.douban.com/j/mobile/" + path,
        data=urllib.parse.urlencode(body).encode("utf-8"),
        headers=douban_form_headers(),
    )
    try:
        with opener.open(req, timeout=20) as response:
            raw = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
    except Exception:
        raise ValueError("豆瓣暂时没有回应")
    try:
        data = json.loads(raw)
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    updated = jar_dict(jar)
    with DOUBAN_LOCK:
        save_pending_cookies(updated)
    return data, updated, opener


def ticket_fields(body):
    ticket = text_of(body.get("ticket"), 2048)
    randstr = text_of(body.get("randstr"), 128)
    app_id = text_of(body.get("tcAppId"), 20)
    if ticket and randstr and re.fullmatch(r"\d{4,20}", app_id):
        return {"ticket": ticket, "randstr": randstr, "tc_app_id": app_id}
    return {}


def phone_parts(body):
    area = text_of(body.get("areaCode"), 6) or "+86"
    number = re.sub(r"\s+", "", text_of(body.get("phone"), 20))
    if not AREA_RE.fullmatch(area):
        raise ValueError("区号不对")
    if area == "+86":
        if not PHONE_RE.fullmatch(number):
            raise ValueError("请填写11位手机号")
    elif not re.fullmatch(r"\d{6,15}", number):
        raise ValueError("手机号不对")
    return area, number


def douban_captcha_image(opener, url):
    url = str(url or "")
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/"):
        url = "https://accounts.douban.com" + url
    host = urllib.parse.urlparse(url).netloc.lower()
    if not url.startswith("http") or not (host.endswith("douban.com") or host.endswith("doubanio.com")):
        return ""
    try:
        with opener.open(urllib.request.Request(url, headers={
            "User-Agent": DOUBAN_UA,
            "Referer": "https://accounts.douban.com/passport/login",
        }), timeout=15) as response:
            data = response.read()
            ctype = (response.headers.get("Content-Type") or "image/jpeg").split(";")[0].strip().lower()
    except Exception:
        return ""
    if not data or len(data) > 200000 or not ctype.startswith("image/"):
        return ""
    return "data:%s;base64,%s" % (ctype, base64.b64encode(data).decode("ascii"))


def captcha_challenge(data, opener):
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    message = str(data.get("message") or "")
    image_url = str(payload.get("captcha_image_url") or "")
    if message != "captcha_required" and not image_url and not payload.get("touch_cap_url"):
        return None
    url = str(payload.get("touch_cap_url") or "")
    app_id = str(payload.get("tc_app_id") or "")
    if TOUCH_CAP_RE.match(url) and re.fullmatch(r"\d{4,20}", app_id):
        return {
            "ok": False,
            "needCaptcha": True,
            "captchaKind": "slider",
            "touchCapUrl": url,
            "tcAppId": app_id,
        }
    image = douban_captcha_image(opener, image_url) if image_url else ""
    if image:
        return {
            "ok": False,
            "needCaptcha": True,
            "captchaKind": "image",
            "captchaId": payload.get("captcha_id") or "",
            "captchaImage": image,
        }
    if image_url:
        return {"error": "豆瓣验证码没有加载出来", "code": 502}
    return {"error": douban_error_text(data), "code": 400}


def douban_interest_fields(ck, status, review=None):
    interest = PAGE_STATUS_TO_DOUBAN.get(status or "")
    if not interest:
        raise ValueError("状态不对")
    review = clean_review(review or {})
    fields = {"ck": ck, "interest": interest, "rating": "", "fold": "F", "foldcollect": "F", "tags": "", "comment": ""}
    if status == "read":
        fields.update(rating=str(review["personalRating"] or ""), tags=" ".join(review["tags"]), comment=review["comment"])
    # An unchecked checkbox is omitted, as in the real Douban form. No `private=false` truthy string.
    if review["doubanPrivate"]:
        fields["private"] = "on"
    return fields


def mark_douban_interest(cookies, sid, status, review=None):
    """把一部片子标进已登录的豆瓣。不在这里删除。"""
    if not re.fullmatch(r"\d{1,12}", str(sid or "")):
        raise ValueError("没有豆瓣链接，没法同步")
    interest = PAGE_STATUS_TO_DOUBAN.get(status or "")
    if not interest:
        raise ValueError("状态不对")
    opener, jar = opener_from_cookies(cookies)
    try:
        opener.open(urllib.request.Request(
            "https://book.douban.com/subject/%s/" % sid,
            headers={"User-Agent": DOUBAN_UA},
        ), timeout=15).read()
    except Exception:
        pass
    ck = jar_dict(jar).get("ck") or (cookies or {}).get("ck") or ""
    if not ck:
        raise ValueError("豆瓣登录已失效，请重新登录")
    fields = douban_interest_fields(ck, status, review)
    req = urllib.request.Request(
        "https://book.douban.com/j/subject/%s/interest" % sid,
        data=urllib.parse.urlencode(fields).encode("utf-8"),
        headers={
            "User-Agent": DOUBAN_UA,
            "Origin": "https://book.douban.com",
            "Referer": "https://book.douban.com/subject/%s/" % sid,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    try:
        with opener.open(req, timeout=20) as response:
            raw = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        if exc.code in (401, 403):
            raise ValueError("豆瓣登录已失效，请重新登录")
    except Exception:
        raise ValueError("豆瓣暂时没有回应")
    if raw.lstrip().startswith("<"):
        raise ValueError("豆瓣没有收下，过几分钟再试")
    try:
        data = json.loads(raw)
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    if data.get("r") in (0, "0") or data.get("status") == "success":
        updated = jar_dict(jar)
        if uid_from_cookies(updated):
            save_douban_session(updated)
        return
    message = str(data.get("msg") or data.get("message") or "")
    if "登录" in message or "登录" in raw:
        raise ValueError("豆瓣登录已失效，请重新登录")
    raise ValueError((message or "没有写进豆瓣")[:80])


def complete_douban_login(cookies):
    if not uid_from_cookies(cookies):
        return ""
    if not douban_session_ok(cookies):
        raise ValueError("豆瓣没有登录成功")
    uid = save_douban_session(cookies)
    clear_pending_cookies()
    return uid


def douban_session_ok(cookies):
    opener, _jar = opener_from_cookies(cookies, follow_redirect=False)
    req = urllib.request.Request("https://www.douban.com/settings/", headers={"User-Agent": DOUBAN_UA})
    try:
        with opener.open(req, timeout=15) as response:
            return response.status == 200
    except urllib.error.HTTPError as exc:
        if exc.code in (301, 302, 303, 307, 308):
            location = exc.headers.get("Location") or ""
            if "accounts.douban.com" in location or "passport/login" in location:
                return False
            return True
        raise ValueError("豆瓣暂时没有回应")
    except ValueError:
        raise
    except Exception:
        raise ValueError("豆瓣暂时没有回应")


def douban_error_text(data):
    message = str((data or {}).get("message") or "")
    description = str((data or {}).get("description") or "")
    if "密码" in description or "用户名" in description:
        return "豆瓣账号或密码不对"
    if "denied" in message.lower() or "denied" in description.lower():
        return "豆瓣拒绝了这次登录，过几分钟再试"
    if description and not description.isascii():
        return description[:80]
    return "豆瓣没有登录成功"


def parse_pub(text):
    """<div class="pub"> 的格式：作者 / 译者 / 出版社 / 年份 / 价格。

    译者和价格都可能没有，所以以「含年份的那一段」为锚点往前推，
    比按固定下标取更稳。
    """
    parts = [part.strip() for part in str(text or "").split("/") if part.strip()]
    year_index = -1
    for index, part in enumerate(parts):
        if re.search(r"(?:19|20)\d{2}", part):
            year_index = index
            break
    if year_index < 0:
        return "", "", "", ""
    year_match = re.search(r"(?:19|20)\d{2}", parts[year_index])
    return (
        parts[0] if year_index >= 1 else "",
        parts[1] if year_index >= 3 else "",
        parts[year_index - 1] if year_index >= 1 else "",
        int(year_match.group(0)) if year_match else "",
    )


def parse_collect_html(html_text, start):
    """解析豆瓣读书的收藏页。

    电影版的收藏页是 <div class="item"> + <em>，读书版完全不同：
    卡片是 <li class="subject-item">，书名在 <h2><a title="...">，
    作者/译者/出版社/年份/价格挤在 <div class="pub"> 里，用 / 分隔。
    """
    total = 0
    shown_end = None
    match = re.search(
        r"subject-num\">\s*(\d+)\s*-\s*(\d+)(?:&nbsp;|\xa0|\s)*/(?:&nbsp;|\xa0|\s)*(\d+)",
        html_text,
    )
    if match:
        shown_end = int(match.group(2))
        total = int(match.group(3))

    cards = []
    for part in re.split(r'<li class="subject-item"', html_text)[1:]:
        sid_match = re.search(r"/subject/(\d+)/", part)
        if not sid_match:
            continue

        title = ""
        title_match = re.search(r'<h2>\s*<a[^>]*?title="([^"]*)"', part, re.S)
        if title_match:
            title = html.unescape(title_match.group(1))
        if not title:
            link_match = re.search(r"<h2>\s*<a[^>]*>(.*?)</a>", part, re.S)
            if link_match:
                title = html.unescape(re.sub(r"<[^>]+>", "", link_match.group(1)))
        title = re.sub(r"\s+", " ", title).strip()
        if not title:
            continue

        img_match = re.search(r'<img[^>]+src="([^"]+)"', part)
        poster = html.unescape(img_match.group(1)) if img_match else ""
        if poster.startswith("//"):
            poster = "https:" + poster

        pub = ""
        year = ""
        pub_match = re.search(r'<div class="pub">(.*?)</div>', part, re.S)
        if pub_match:
            pub = html.unescape(re.sub(r"<[^>]+>", " ", pub_match.group(1)))
            pub = re.sub(r"\s+", " ", pub).strip()
            year_match = re.search(r"(?:19|20)\d{2}", pub)
            if year_match:
                year = int(year_match.group(0))

        cards.append({
            "sid": sid_match.group(1),
            "title": title[:200],
            "titleEn": "",
            "year": year,
            "poster": poster if poster.startswith("http") else "",
            "pub": pub,
        })

    if shown_end is None:
        shown_end = start + (len(cards) or DOUBAN_GRID_PAGE)
    return cards, total, shown_end

def fetch_collect_page(opener, uid, status, start):
    query = urllib.parse.urlencode({
        "start": start,
        "sort": "time",
        "rating": "all",
        "filter": "all",
        "mode": "grid",
    })
    url = "https://book.douban.com/people/%s/%s?%s" % (
        urllib.parse.quote(uid), COLLECT_KIND[status], query,
    )
    req = urllib.request.Request(url, headers={
        "User-Agent": DOUBAN_UA,
        "Referer": "https://book.douban.com/people/%s/" % urllib.parse.quote(uid),
    })
    try:
        with opener.open(req, timeout=20) as response:
            final_url = response.geturl()
            page = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise ValueError("豆瓣登录已失效，请重新登录")
        raise ValueError("豆瓣暂时没有回应")
    except ValueError:
        raise
    except Exception:
        raise ValueError("豆瓣暂时没有回应")
    if "accounts.douban.com" in final_url:
        raise ValueError("豆瓣登录已失效，请重新登录")
    return parse_collect_html(page, start)


def book_from_card(card, status):
    info = fetch_book(card["sid"]) or {}
    # 详情接口偶尔会被限流；收藏页的 pub 字段能兜住作者、译者、出版社和年份。
    pub_author, pub_translator, pub_publisher, pub_year = parse_pub(card.get("pub") or "")
    poster = card["poster"] if str(card.get("poster") or "").startswith("http") else ""
    return clean_book({
        "title": card["title"],
        "titleEn": card.get("titleEn") or "",
        "year": info.get("year") or card.get("year") or pub_year or "",
        "status": DOUBAN_STATUS.get(status, "read"),
        "author": info.get("author") or card.get("author") or pub_author or "",
        "translator": info.get("translator") or ([pub_translator] if pub_translator else []),
        "publishers": info.get("publishers") or card.get("publishers") or ([pub_publisher] if pub_publisher else []),
        "genres": info.get("genres") or [],
        "rating": info.get("rating") if info.get("rating") not in ("", None) else "",
        "douban": "https://book.douban.com/subject/%s/" % card["sid"],
        "poster": poster,
    }, new_id())

def count_added(books):
    counts = {"read": 0, "reading": 0, "want": 0}
    for book in books:
        status = book.get("status") if book.get("status") in counts else "read"
        counts[status] += 1
    return counts

def subject_id_of(book):
    match = SUBJECT_RE.search(book.get("douban") or "")
    return match.group(1) if match else ""


def listed_status(items, book):
    """读过、在读、想读里已经有同一本时，返回它现在的状态。"""
    sid = subject_id_of(book)
    if not sid:
        return ""
    for item in items:
        if subject_id_of(item) != sid:
            continue
        status = item.get("status") or ""
        return status if status in PAGE_STATUS_TO_DOUBAN else "read"
    return ""


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
        if path == "/api/password":
            return self.handle_change_password()
        if path == "/api/douban/login":
            return self.handle_douban_login()
        if path == "/api/douban/phone-code":
            return self.handle_douban_phone_code()
        if path == "/api/douban/phone-login":
            return self.handle_douban_phone_login()
        if path == "/api/douban/logout":
            return self.handle_douban_logout()
        if path == "/api/books/fill-ratings" or path == "/api/books/refresh":
            return self.handle_refresh()
        if path == "/api/books/import-douban":
            return self.handle_import_douban()
        if path == "/api/books":
            return self.handle_create()
        self.send_json({"error": "没有这个接口"}, 404)

    def do_PUT(self):
        path = self.clean_path()
        if path == "/api/books":
            return self.handle_import()
        if path.startswith("/api/books/"):
            return self.handle_update(path.split("/", 3)[3])
        self.send_json({"error": "没有这个接口"}, 404)

    def do_DELETE(self):
        path = self.clean_path()
        if path.startswith("/api/books/"):
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
        with AUTH_LOCK:
            return verify_token(self.config["token_secret"], header[7:].strip())

    def require_auth(self):
        if self.authorized():
            return True
        self.send_json({"error": "请先登录"}, 401)
        return False

    def handle_api_get(self, path):
        if path == "/api/books":
            with LOCK:
                try:
                    items = load_books()
                except ValueError as exc:
                    return self.send_json({"error": str(exc)}, 500)
            return self.send_json(items)
        if path == "/api/me":
            if not self.authorized():
                return self.send_json({"error": "请先登录"}, 401)
            return self.send_json({"ok": True})
        if path == "/api/health":
            return self.send_json({"ok": True})
        if path == "/api/douban/session":
            return self.handle_douban_session()
        if path == "/api/intro":
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            return self.handle_intro(query.get("sid", [""])[0])
        if path.startswith("/api/suggest"):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            return self.handle_suggest(query.get("q", [""])[0].strip(), query.get("start", ["0"])[0])
        if path.startswith("/api/img"):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            return self.handle_img(query.get("url", [""])[0])
        self.send_json({"error": "没有这个接口"}, 404)

    def handle_intro(self, sid):
        sid = str(sid or "")
        if not re.fullmatch(r"\d{1,12}", sid):
            return self.send_json({"error": "没有这本书"}, 400)
        return self.send_json({"intro": fetch_search_intro("book", sid)})

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
        with AUTH_LOCK:
            if not check_password(password, self.config["password_hash"]):
                note_login_failure(ip)
                time.sleep(0.4)
                return self.send_json({"error": "密码不对"}, 401)
            FAILS.pop(ip, None)
            token, exp = make_token(self.config["token_secret"])
        self.send_json({"token": token, "expires": exp})

    def handle_change_password(self):
        if not self.require_auth():
            return
        ip = client_ip_of(self)
        if login_locked(ip):
            return self.send_json({"error": "试得太多了，请 10 分钟后再试"}, 429)
        try:
            body = self.read_json(10_000)
            if not isinstance(body, dict):
                raise ValueError("请求不对")
            with AUTH_LOCK:
                if not self.require_auth():
                    return
                change_management_password(self.config, body.get("current_password"),
                                           body.get("new_password"), body.get("confirm_password"))
                FAILS.pop(ip, None)
        except ValueError as exc:
            if str(exc) == "当前管理密码不正确":
                note_login_failure(ip)
            return self.send_json({"error": str(exc)}, 400)
        except OSError:
            return self.send_json({"error": "密码保存失败，原密码仍有效，请检查服务器文件权限"}, 500)
        self.send_json({"ok": True})

    def handle_create(self):
        if not self.require_auth():
            return
        try:
            body = self.read_json()
            book = clean_book(body, new_id())
            book = enrich_book(book)
        except ValueError as exc:
            return self.send_json({"error": str(exc)}, 400)
        sync = isinstance(body, dict) and body.get("syncDouban") is True
        with LOCK:
            try:
                items = load_books()
            except ValueError as exc:
                return self.send_json({"error": str(exc)}, 500)
            if len(items) >= 5000:
                return self.send_json({"error": "书单已经太多了"}, 400)
            listed = listed_status(items, book)
            items.append(book)
            save_books(items)
        if sync and listed:
            douban_sync = {"ok": True, "skipped": True, "status": listed}
        else:
            douban_sync = self.sync_new_book(book) if sync else None
        self.send_json({"ok": True, "item": book, "items": items, "doubanSync": douban_sync})

    def sync_new_book(self, book):
        session = load_douban_session()
        if not session:
            return {"ok": False, "error": "请先登录豆瓣"}
        sid = subject_id_of(book)
        if not sid:
            return {"ok": False, "error": "没有豆瓣链接，没法同步"}
        try:
            mark_douban_interest(session["cookies"], sid, book.get("status") or "read", book)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True}

    def handle_update(self, book_id):
        if not self.require_auth():
            return
        book_id = urllib.parse.unquote(book_id)
        try:
            body = self.read_json()
            book = clean_book(body, book_id)
            book = enrich_book(book)
        except ValueError as exc:
            return self.send_json({"error": str(exc)}, 400)
        sync = isinstance(body, dict) and body.get("syncDouban") is True
        with LOCK:
            try:
                items = load_books()
            except ValueError as exc:
                return self.send_json({"error": str(exc)}, 500)
            found = False
            for index, item in enumerate(items):
                if item.get("id") == book_id:
                    for key, default in (("personalRating", ""), ("tags", []), ("comment", ""), ("doubanPrivate", False)):
                        if key not in body:
                            book[key] = item.get(key, default)
                    items[index] = book
                    found = True
                    break
            if not found:
                return self.send_json({"error": "没有这部片子"}, 404)
            save_books(items)
        douban_sync = self.sync_new_book(book) if sync else None
        self.send_json({"ok": True, "item": book, "items": items, "doubanSync": douban_sync})

    def handle_delete(self, book_id):
        if not self.require_auth():
            return
        book_id = urllib.parse.unquote(book_id)
        with LOCK:
            try:
                items = load_books()
            except ValueError as exc:
                return self.send_json({"error": str(exc)}, 500)
            kept = [item for item in items if item.get("id") != book_id]
            if len(kept) == len(items):
                return self.send_json({"error": "没有这部片子"}, 404)
            save_books(kept)
        self.send_json({"ok": True, "items": kept})

    def handle_refresh(self):
        if not self.require_auth():
            return
        with LOCK:
            try:
                items = load_books()
            except ValueError as exc:
                return self.send_json({"error": str(exc)}, 500)
        changed = 0
        attempts = 0
        more = False
        for book in items:
            if not SUBJECT_RE.search(book.get("douban") or ""):
                continue
            before = {
                "rating": book.get("rating"),
                "author": book.get("author"),
                "translator": list(book.get("translator") or []),
                "genres": list(book.get("genres") or []),
                "publishers": list(book.get("publishers") or []),
                "year": book.get("year"),
            }
            if not (
                before["rating"] in ("", None)
                or not before["author"]
                or not before["translator"]
                or not before["genres"]
                or not before["publishers"]
                or before["year"] in ("", None)
            ):
                continue
            attempts += 1
            if attempts > 40:
                more = True
                break
            enrich_book(book)
            if apply_missing(before, book):
                changed += 1
        if changed:
            with LOCK:
                try:
                    current = load_books()
                except ValueError as exc:
                    return self.send_json({"error": str(exc)}, 500)
                filled = {book.get("id"): book for book in items}
                for index, book in enumerate(current):
                    updated = filled.get(book.get("id"))
                    if updated and apply_missing(book, updated):
                        current[index] = book
                save_books(current)
                items = current
        self.send_json({"ok": True, "filled": changed, "more": more, "items": items})

    def handle_douban_session(self):
        if not self.require_auth():
            return
        session = load_douban_session()
        if not session:
            return self.send_json({"ok": True, "loggedIn": False})
        self.send_json({"ok": True, "loggedIn": True, "uid": session["uid"]})

    def handle_douban_logout(self):
        if not self.require_auth():
            return
        clear_douban_session()
        clear_pending_cookies()
        self.send_json({"ok": True})

    def reply_douban_auth(self, data, cookies):
        try:
            uid = complete_douban_login(cookies)
        except ValueError as exc:
            return self.send_json({"error": str(exc)}, 502)
        if not uid:
            return self.send_json({"error": douban_error_text(data)}, 400)
        self.send_json({"ok": True, "uid": uid})

    def handle_douban_login(self):
        if not self.require_auth():
            return
        try:
            body = self.read_json()
        except ValueError as exc:
            return self.send_json({"error": str(exc)}, 400)
        if not isinstance(body, dict):
            return self.send_json({"error": "格式不对"}, 400)
        account = text_of(body.get("account"), 80)
        password = body.get("password") if isinstance(body.get("password"), str) else ""
        password = password[:200]
        captcha_id = text_of(body.get("captchaId"), 80)
        captcha_solution = text_of(body.get("captcha"), 20)
        if not account or not password:
            return self.send_json({"error": "请填写豆瓣账号和密码"}, 400)
        fields = {"name": account, "password": password, "remember": "true"}
        fields.update(ticket_fields(body))
        if captcha_id and captcha_solution:
            fields["captcha_id"] = captcha_id
            fields["captcha_solution"] = captcha_solution
        try:
            data, cookies, opener = douban_post("login/basic", fields)
        except ValueError as exc:
            return self.send_json({"error": str(exc)}, 502)
        challenge = captcha_challenge(data, opener)
        if challenge:
            if challenge.get("error"):
                return self.send_json({"error": challenge["error"]}, challenge.get("code") or 400)
            return self.send_json(challenge)
        self.reply_douban_auth(data, cookies)

    def handle_douban_phone_code(self):
        if not self.require_auth():
            return
        try:
            body = self.read_json()
        except ValueError as exc:
            return self.send_json({"error": str(exc)}, 400)
        if not isinstance(body, dict):
            return self.send_json({"error": "格式不对"}, 400)
        try:
            area, number = phone_parts(body)
        except ValueError as exc:
            return self.send_json({"error": str(exc)}, 400)
        fields = {"area_code": area, "number": number, "analytics": "analytics_log"}
        fields.update(ticket_fields(body))
        captcha_id = text_of(body.get("captchaId"), 80)
        captcha_solution = text_of(body.get("captcha"), 20)
        if captcha_id and captcha_solution:
            fields["captcha_id"] = captcha_id
            fields["captcha_solution"] = captcha_solution
        try:
            data, _cookies, opener = douban_post("login/request_phone_code", fields)
        except ValueError as exc:
            return self.send_json({"error": str(exc)}, 502)
        challenge = captcha_challenge(data, opener)
        if challenge:
            if challenge.get("error"):
                return self.send_json({"error": challenge["error"]}, challenge.get("code") or 400)
            return self.send_json(challenge)
        if str(data.get("status") or "") == "success":
            return self.send_json({"ok": True, "sent": True})
        self.send_json({"error": douban_error_text(data)}, 400)

    def handle_douban_phone_login(self):
        if not self.require_auth():
            return
        try:
            body = self.read_json()
        except ValueError as exc:
            return self.send_json({"error": str(exc)}, 400)
        if not isinstance(body, dict):
            return self.send_json({"error": "格式不对"}, 400)
        try:
            area, number = phone_parts(body)
        except ValueError as exc:
            return self.send_json({"error": str(exc)}, 400)
        code = text_of(body.get("code"), 8)
        if not re.fullmatch(r"\d{4,8}", code):
            return self.send_json({"error": "请填写短信验证码"}, 400)
        fields = {"area_code": area, "number": number, "code": code}
        fields.update(ticket_fields(body))
        try:
            data, cookies, opener = douban_post("login/verify_phone_code", fields)
        except ValueError as exc:
            return self.send_json({"error": str(exc)}, 502)
        challenge = captcha_challenge(data, opener)
        if challenge:
            if challenge.get("error"):
                return self.send_json({"error": challenge["error"]}, challenge.get("code") or 400)
            return self.send_json(challenge)
        self.reply_douban_auth(data, cookies)

    def handle_import_douban(self):
        if not self.require_auth():
            return
        try:
            body = self.read_json()
        except ValueError as exc:
            return self.send_json({"error": str(exc)}, 400)
        if not isinstance(body, dict):
            return self.send_json({"error": "格式不对"}, 400)
        session = load_douban_session()
        if not session:
            return self.send_json({"error": "请先登录豆瓣"}, 400)
        try:
            if not douban_session_ok(session["cookies"]):
                clear_douban_session()
                return self.send_json({"error": "豆瓣登录已失效，请重新登录"}, 400)
        except ValueError as exc:
            return self.send_json({"error": str(exc)}, 502)
        wanted = body.get("statuses")
        if not isinstance(wanted, list) or not wanted:
            wanted = ["done", "reading", "mark"]
        statuses = [item for item in ("done", "reading", "mark") if item in wanted]
        if not statuses:
            return self.send_json({"error": "请至少选择读过、在读或想读中的一种"}, 400)
        raw_cursors = body.get("cursors") if isinstance(body.get("cursors"), dict) else {}
        full = body.get("full") is True
        with LOCK:
            try:
                current = load_books()
            except ValueError as exc:
                return self.send_json({"error": str(exc)}, 500)
        seen = {sid for sid in (subject_id_of(book) for book in current) if sid}
        already_ids = set(seen)
        fresh = []
        skipped = 0
        duplicate = 0
        status_plan = {}
        more = False
        next_cursors = {}
        progress = {}
        deadline = time.time() + 45
        opener, jar = opener_from_cookies(session["cookies"])
        uid = session["uid"]
        try:
            for status in statuses:
                raw = raw_cursors.get(status, 0)
                if raw == -1 or raw == "-1":
                    next_cursors[status] = -1
                    continue
                try:
                    start = max(0, int(raw or 0))
                except (TypeError, ValueError):
                    start = 0
                finished = False
                caught_up = False
                read = start
                total_count = 0
                empty_tries = 0
                while True:
                    if time.time() > deadline or len(fresh) >= 2000:
                        break
                    cards, total_count, shown_end = fetch_collect_page(opener, uid, status, start)
                    if not cards:
                        if total_count and read < total_count and empty_tries < 2:
                            empty_tries += 1
                            time.sleep(0.4)
                            continue
                        if not total_count or read >= total_count:
                            finished = True
                            break
                        start = max(start + DOUBAN_GRID_PAGE, shown_end or 0)
                        read = min(start, total_count) if total_count else start
                        if total_count and start >= total_count:
                            finished = True
                            break
                        continue
                    empty_tries = 0
                    page_done = True
                    page_known = True
                    new_status = DOUBAN_STATUS.get(status, "read")
                    for card in cards:
                        sid = card["sid"]
                        if sid in already_ids:
                            status_plan[sid] = new_status
                            skipped += 1
                            continue
                        page_known = False
                        if sid in seen:
                            duplicate += 1
                            continue
                        try:
                            book = book_from_card(card, status)
                        except ValueError:
                            continue
                        seen.add(sid)
                        fresh.append(book)
                        if time.time() > deadline:
                            page_done = False
                            break
                    if not page_done:
                        break
                    start = max(start + 1, shown_end)
                    read = min(start, total_count) if total_count else start
                    if total_count and start >= total_count:
                        finished = True
                        break
                    if page_known and not full:
                        finished = True
                        caught_up = True
                        break
                    time.sleep(0.12)
                progress[status] = {
                    "read": read,
                    "total": total_count,
                    "done": finished,
                    "caughtUp": caught_up,
                }
                next_cursors[status] = -1 if finished else start
                if not finished:
                    more = True
                    break
            updated = jar_dict(jar)
            if uid_from_cookies(updated):
                save_douban_session(updated)
        except ValueError as exc:
            return self.send_json({"error": str(exc)}, 502)
        for status in statuses:
            if status in next_cursors:
                continue
            raw = raw_cursors.get(status, 0)
            if raw == -1 or raw == "-1":
                next_cursors[status] = -1
                continue
            try:
                next_cursors[status] = max(0, int(raw or 0))
            except (TypeError, ValueError):
                next_cursors[status] = 0
        inserted = []
        with LOCK:
            try:
                current = load_books()
            except ValueError as exc:
                return self.send_json({"error": str(exc)}, 500)
            have = {sid for sid in (subject_id_of(book) for book in current) if sid}
            status_changed = 0
            if status_plan:
                for book in current:
                    sid = subject_id_of(book)
                    new_status = status_plan.get(sid)
                    if new_status and book.get("status") != new_status:
                        book["status"] = new_status
                        status_changed += 1
            for book in fresh:
                sid = subject_id_of(book)
                if sid in have:
                    if sid in already_ids:
                        skipped += 1
                    else:
                        duplicate += 1
                    continue
                have.add(sid)
                current.append(book)
                inserted.append(book)
            if inserted or status_changed:
                save_books(current)
        caught_up = any(item.get("caughtUp") for item in progress.values())
        self.send_json({
            "ok": True,
            "added": len(inserted),
            "updated": status_changed,
            "counts": count_added(inserted),
            "skipped": skipped,
            "duplicate": duplicate,
            "caughtUp": caught_up and not more,
            "more": more,
            "progress": progress,
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
                book_id = raw.get("id") if isinstance(raw, dict) else ""
                if not isinstance(book_id, str) or not ID_RE.match(book_id) or book_id in used:
                    book_id = new_id()
                used.add(book_id)
                items.append(clean_book(raw, book_id))
        except ValueError as exc:
            return self.send_json({"error": str(exc)}, 400)
        with LOCK:
            save_books(items)
        self.send_json({"ok": True, "items": items})

    def handle_suggest(self, keyword, start="0"):
        try:
            start = int(start)
            if start < 0 or start > 100000:
                raise ValueError()
        except (ValueError, TypeError):
            return self.send_json({"error": "搜索页码不正确"}, 400)
        if not keyword:
            return self.send_json({"results": [], "nextStart": start, "hasMore": False})
        try:
            out = suggest_douban(keyword, start)
        except Exception:
            return self.send_json({"error": "豆瓣搜索暂时没有回应"}, 502)
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
            "Referer": "https://book.douban.com/",
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
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8003
    Handler.config = load_config()
    ThreadingHTTPServer.allow_reuse_address = True
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("书单服务已启动: http://127.0.0.1:%d （按 Ctrl+C 停止）" % port)
    print("对外地址由 nginx 的 5004 端口提供 https。")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
