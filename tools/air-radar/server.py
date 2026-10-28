# -*- coding: utf-8 -*-
"""
【2026-10-28 新增】飞机雷达数据转发服务

放在你自己有公网 IP 的服务器上运行（本项目部署在 47.103.222.155）。
- 纯 Python 标准库，不需要 pip install 任何东西
- 职责：替网页前端向 adsb.lol 要实时航班数据，解决浏览器跨域拦截；
  顺手做 8 秒缓存和按 IP 限流，避免把上游免费接口打爆
- 前端页面（https://hlmdf.github.io/tools/air-radar/）通过 HTTPS 跨域调用本服务

接口：
  GET /api/aircraft?lat=30.6&lon=114.3&r=150
      lat/lon 是视野中心经纬度，r 是查询半径（海里，10~250）
      返回 {"ac":[...],"total":n,"now":毫秒时间戳}，ac 里只保留前端需要的字段
  GET /api/photo?hex=780c25
      【2026-10-28 新增】按飞机 hex 查实拍照片（上游 planespotters.net），
      返回 {"photo":{"src":缩略图,"link":原图页,"photographer":作者}} 或 {"photo":null}

服务器上用 deploy/install.sh 安装：Nginx 在 5011 提供 HTTPS，本进程只监听 127.0.0.1:8011。
本地试跑：
    python server.py --host 127.0.0.1 --port 8011
"""

import argparse
import json
import ssl
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 上游：adsb.lol 的 readsb v2 接口，免费公开、无需密钥
UPSTREAM = "https://api.adsb.lol/v2/point/{lat:.4f}/{lon:.4f}/{r:d}"
UPSTREAM_TIMEOUT = 8  # 秒
# 【2026-10-28 修改】5 秒缓存，跟前端 6 秒刷新节奏对齐；
# 同一查询网格内多个访客共享一份缓存，避免把上游免费接口打爆
CACHE_TTL_SECONDS = 5
# 缓存按 0.25° 经纬网格聚合，附近视野共享一份结果
GRID = 0.25
# 每个 IP 每分钟最多请求多少次（防个别用户刷接口）
RATE_LIMIT_PER_MINUTE = 30
MIN_RADIUS_NM = 10
MAX_RADIUS_NM = 250  # 上游接口上限

# 前端弹窗只展示这些字段，其余（几十个）在转发时丢掉，省流量
KEEP_FIELDS = ("hex", "flight", "lat", "lon", "alt_baro", "gs", "track", "t", "r", "squawk", "baro_rate")

# 【2026-10-28 新增】实拍照片上游：planespotters.net，要求 UA 写明应用和联系方式
PHOTO_UPSTREAM = "https://api.planespotters.net/pub/photos/hex/{hex}"
PHOTO_CACHE_TTL_SECONDS = 3600  # 照片不常变，缓存 1 小时

cache_lock = threading.Lock()
cache = {}  # key: (lat_grid, lon_grid, r) -> (时间戳, 响应体)
photo_cache = {}  # key: hex -> (时间戳, 响应体)
rate_lock = threading.Lock()
rate_table = {}  # key: ip -> [窗口起点, 次数]


def cache_key(lat, lon, r):
    return (round(lat / GRID), round(lon / GRID), r)


def rate_ok(ip):
    """滑动窗口限流：一分钟内超过 RATE_LIMIT_PER_MINUTE 次就拒绝"""
    now = time.time()
    with rate_lock:
        entry = rate_table.get(ip)
        if not entry or now - entry[0] >= 60:
            rate_table[ip] = [now, 1]
            return True
        entry[1] += 1
        # 顺手清掉太老的条目，避免表无限涨
        if len(rate_table) > 10000:
            for k in [k for k, v in rate_table.items() if now - v[0] >= 60]:
                del rate_table[k]
        return entry[1] <= RATE_LIMIT_PER_MINUTE


def fetch_upstream(lat, lon, r):
    """向上游要数据并瘦身，带 8 秒网格缓存。失败抛异常。"""
    key = cache_key(lat, lon, r)
    now = time.time()
    with cache_lock:
        hit = cache.get(key)
        if hit and now - hit[0] < CACHE_TTL_SECONDS:
            return hit[1]

    url = UPSTREAM.format(lat=lat, lon=lon, r=r)
    req = urllib.request.Request(url, headers={"User-Agent": "hlmdf-air-radar/1.0"})
    with urllib.request.urlopen(req, timeout=UPSTREAM_TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    acs = data.get("ac") or []
    slim = [{k: ac[k] for k in KEEP_FIELDS if k in ac} for ac in acs]
    body = {"ac": slim, "total": len(slim), "now": int(now * 1000)}

    with cache_lock:
        cache[key] = (now, body)
        # 缓存表也别无限涨，超过 500 格就把最旧的一半扔掉
        if len(cache) > 500:
            for k in sorted(cache, key=lambda k: cache[k][0])[: len(cache) // 2]:
                del cache[k]
    return body


def fetch_photo(hexcode):
    """【2026-10-28 新增】查飞机实拍照片，带 1 小时缓存；查不到/出错都返回 {"photo": None}"""
    now = time.time()
    with cache_lock:
        hit = photo_cache.get(hexcode)
        if hit and now - hit[0] < PHOTO_CACHE_TTL_SECONDS:
            return hit[1]

    photo = None
    try:
        url = PHOTO_UPSTREAM.format(hex=hexcode)
        req = urllib.request.Request(url, headers={"User-Agent": "hlmdf-air-radar/1.0 (+https://hlmdf.github.io)"})
        with urllib.request.urlopen(req, timeout=UPSTREAM_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        photos = data.get("photos") or []
        if photos:
            p = photos[0]
            thumb = p.get("thumbnail_large") or p.get("thumbnail") or {}
            src = thumb.get("src")
            if src:
                photo = {
                    "src": src,
                    "link": p.get("link") or "",
                    "photographer": p.get("photographer") or "",
                }
    except Exception:
        photo = None

    body = {"photo": photo}
    with cache_lock:
        photo_cache[hexcode] = (now, body)
        if len(photo_cache) > 5000:
            for k in sorted(photo_cache, key=lambda k: photo_cache[k][0])[: len(photo_cache) // 2]:
                del photo_cache[k]
    return body


def valid_coord(lat, lon):
    if isinstance(lat, bool) or isinstance(lon, bool):
        return False
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return False
    return -90 <= float(lat) <= 90 and -180 <= float(lon) <= 180


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "AirRadar/1.0"

    def log_message(self, fmt, *args):
        pass  # 不打印访问日志，避免刷屏

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _client_ip(self):
        # 只相信本机反代写上的地址，公网直连时忽略客户端自带的转发头
        peer = self.client_address[0]
        if peer in ("127.0.0.1", "::1"):
            for header in ("X-Real-IP", "X-Forwarded-For"):
                value = self.headers.get(header)
                if value:
                    return value.split(",")[0].strip()
        return peer

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self._cors()
        self.end_headers()

    def do_GET(self):
        path, _, query = self.path.partition("?")
        path = path.rstrip("/") or "/"

        if path in ("/", "/health"):
            self._send_json({"ok": True})
            return

        if not rate_ok(self._client_ip()):
            self._send_json({"error": "rate limited"}, 429)
            return

        params = urllib.parse.parse_qs(query)

        # 【2026-10-28 新增】飞机实拍照片转发
        if path == "/api/photo":
            hexcode = params.get("hex", [""])[0].strip().lower()
            if not (1 <= len(hexcode) <= 8) or not hexcode.isalnum():
                self._send_json({"error": "bad hex"}, 400)
                return
            self._send_json(fetch_photo(hexcode))
            return

        if path != "/api/aircraft":
            self._send_json({"error": "not found"}, 404)
            return

        try:
            lat = float(params.get("lat", [""])[0])
            lon = float(params.get("lon", [""])[0])
            r = int(float(params.get("r", [""])[0]))
        except (TypeError, ValueError):
            self._send_json({"error": "bad lat/lon/r"}, 400)
            return

        if not valid_coord(lat, lon) or not MIN_RADIUS_NM <= r <= MAX_RADIUS_NM:
            self._send_json(
                {"error": "lat/lon out of range or r not in %d..%d" % (MIN_RADIUS_NM, MAX_RADIUS_NM)},
                400,
            )
            return

        try:
            self._send_json(fetch_upstream(lat, lon, r))
        except Exception:
            self._send_json({"error": "upstream unavailable"}, 502)


def main():
    parser = argparse.ArgumentParser(description="飞机雷达数据转发服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=5011, help="监听端口")
    parser.add_argument("--cert", default="", help="TLS 证书链路径（可选）")
    parser.add_argument("--key", default="", help="TLS 私钥路径（可选）")
    args = parser.parse_args()

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    scheme = "http"

    if args.cert and args.key:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(args.cert, args.key)
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
        scheme = "https"

    print("飞机雷达转发服务已启动：%s://%s:%d" % (scheme, args.host, args.port))
    print("  查询航班 GET %s://%s:%d/api/aircraft?lat=30.6&lon=114.3&r=150" % (scheme, args.host, args.port))
    print("按 Ctrl+C 停止。")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")


if __name__ == "__main__":
    main()
