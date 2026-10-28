# -*- coding: utf-8 -*-
"""
【2026-10-28 新增】飞机雷达数据转发服务

放在你自己有公网 IP 的服务器上运行（本项目部署在 47.103.222.155）。
- 纯 Python 标准库，不需要 pip install 任何东西
- 职责：替网页前端向 adsb.lol 要实时航班数据，解决浏览器跨域拦截；
  顺手做 8 秒缓存和按 IP 限流，避免把上游免费接口打爆
- 前端页面（https://hlmdf.github.io/air-radar/）通过 HTTPS 跨域调用本服务

接口：
  GET /api/aircraft?lat=30.6&lon=114.3&r=150
      lat/lon 是视野中心经纬度，r 是查询半径（海里，10~250）
      【2026-10-28 修改】lat/lon 支持逗号分隔的多个中心点（最多 4 个），
      服务端逐点查询后按 hex 去重合并，用于缩小地图时覆盖更大范围
      返回 {"ac":[...],"total":n,"now":毫秒时间戳}，ac 里只保留前端需要的字段
  GET /api/photo?hex=780c25
      【2026-10-28 新增】按飞机 hex 查实拍照片（上游 planespotters.net），
      返回 {"photo":{"src":缩略图,"link":原图页,"photographer":作者}} 或 {"photo":null}
  GET /api/route?callsign=CES2067
      【2026-10-28 新增】按航班号查起降机场（上游 adsbdb.com），
      返回 {"route":{"origin":{"code","name"},"destination":{...}}} 或 {"route":null}

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

# 上游：adsb.lol 为主，adsb.fi 为备用（两个免费公开接口，无需密钥）
# 【2026-10-28 修改】改为双源 + 多点合并：
#   1. 两个源实测数据几乎一致（武汉 463km：32 vs 31，合并 33），互为兜底而非简单叠加
#   2. 上游限流很严格（5 个并行请求只成功 2 个），所以所有请求串行、间隔 >= 1 秒
#   3. 前端可一次传多个中心点（缩小地图看大范围时用），服务端逐点查询后按 hex 合并
UPSTREAM_PRIMARY = "https://api.adsb.lol/v2/point/{lat:.4f}/{lon:.4f}/{r:d}"
UPSTREAM_FALLBACK = "https://opendata.adsb.fi/api/v2/lat/{lat:.4f}/lon/{lon:.4f}/dist/{r:d}"
UPSTREAM_TIMEOUT = 8  # 秒
# 相邻两次上游请求至少间隔多少秒（上游 1 req/s 量级的限流）
UPSTREAM_MIN_GAP = 1.1
# 【2026-10-28 修改】缓存 8 秒，跟前端 8 秒刷新节奏对齐；
# 同一查询网格内多个访客共享一份缓存，避免把上游免费接口打爆
CACHE_TTL_SECONDS = 8
# 上游限流/超时时，最多返回多少秒以内的旧数据（宁可显示旧一点也别空屏）
STALE_TTL_SECONDS = 90
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

# 【2026-10-28 新增】航路查询上游：adsbdb.com，按航班号返回起降机场，免密钥
# 航路基本不变，缓存 24 小时
ROUTE_UPSTREAM = "https://api.adsbdb.com/v0/callsign/{callsign}"
ROUTE_CACHE_TTL_SECONDS = 86400

cache_lock = threading.Lock()
cache = {}  # key: (lat_grid, lon_grid, r) -> (时间戳, 飞机列表)
photo_cache = {}  # key: hex -> (时间戳, 响应体)
# 【2026-10-28 新增】航路缓存：key 航班号 -> (时间戳, 响应体)
route_cache = {}
rate_lock = threading.Lock()
rate_table = {}  # key: ip -> [窗口起点, 次数]
# 【2026-10-28 新增】上游串行节流：保证两次请求之间有最小间隔，避免触发上游限流
upstream_lock = threading.Lock()
upstream_last_at = [0.0]

# 一次请求最多查几个中心点（前端缩小地图时用 4 个点拼出更大覆盖）
MAX_POINTS = 4


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


def _upstream_get(url, ua):
    """带全局节流的上游 GET，返回解析后的 JSON；失败抛异常"""
    with upstream_lock:
        wait = UPSTREAM_MIN_GAP - (time.time() - upstream_last_at[0])
        if wait > 0:
            time.sleep(wait)
        upstream_last_at[0] = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": ua})
        with urllib.request.urlopen(req, timeout=UPSTREAM_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))


def _slim(acs):
    return [{k: ac[k] for k in KEEP_FIELDS if k in ac} for ac in acs]


def fetch_point(lat, lon, r):
    """查一个中心点，返回瘦身后的飞机列表。

    【2026-10-28 修改】双源兜底 + 旧数据兜底：
      - 先问 adsb.lol；被限流/出错再问 adsb.fi（两个源实测基本是同一批飞机）
      - 两个源都失败时，返回 90 秒内的旧缓存，避免地图突然清空
    """
    key = cache_key(lat, lon, r)
    now = time.time()
    with cache_lock:
        hit = cache.get(key)
        if hit and now - hit[0] < CACHE_TTL_SECONDS:
            return hit[1]

    acs = None
    ua = "hlmdf-air-radar/1.0 (+https://hlmdf.github.io)"
    for url in (
        UPSTREAM_PRIMARY.format(lat=lat, lon=lon, r=r),
        UPSTREAM_FALLBACK.format(lat=lat, lon=lon, r=r),
    ):
        try:
            data = _upstream_get(url, ua)
            # adsb.lol 用 ac，adsb.fi 用 aircraft
            acs = data.get("ac") if isinstance(data.get("ac"), list) else data.get("aircraft")
            if acs is not None:
                break
        except Exception:
            continue

    if acs is None:
        with cache_lock:
            hit = cache.get(key)
        if hit and now - hit[0] < STALE_TTL_SECONDS:
            return hit[1]
        raise RuntimeError("upstream unavailable")

    slim = _slim(acs)
    with cache_lock:
        cache[key] = (now, slim)
        # 缓存表也别无限涨，超过 500 格就把最旧的一半扔掉
        if len(cache) > 500:
            for k in sorted(cache, key=lambda k: cache[k][0])[: len(cache) // 2]:
                del cache[k]
    return slim


def fetch_area(points, r):
    """【2026-10-28 新增】查询多个中心点并去重合并。

    前端把视野切成最多 4 个点（缩小地图看大范围时），这里逐点串行查询
    （上游限流只允许 1 req/s 量级），任一点失败就跳过，不影响其它点。
    """
    merged = {}
    for lat, lon in points[:MAX_POINTS]:
        try:
            for ac in fetch_point(lat, lon, r):
                merged[ac.get("hex") or ""] = ac
        except Exception:
            continue
    merged.pop("", None)
    return {"ac": list(merged.values()), "total": len(merged), "now": int(time.time() * 1000)}


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


def fetch_route(callsign):
    """【2026-10-28 新增】按航班号查起降机场，带 24 小时缓存。

    返回 {"route": {"origin": {"code","name"}, "destination": {"code","name"}}}；
    查不到（常见于小众/货运航班）返回 {"route": None}。
    """
    now = time.time()
    with cache_lock:
        hit = route_cache.get(callsign)
        if hit and now - hit[0] < ROUTE_CACHE_TTL_SECONDS:
            return hit[1]

    route = None
    try:
        url = ROUTE_UPSTREAM.format(callsign=urllib.parse.quote(callsign))
        req = urllib.request.Request(url, headers={"User-Agent": "hlmdf-air-radar/1.0 (+https://hlmdf.github.io)"})
        with urllib.request.urlopen(req, timeout=UPSTREAM_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        fr = (data.get("response") or {}).get("flightroute") or {}
        origin = fr.get("origin") or {}
        destination = fr.get("destination") or {}
        if origin and destination:
            def pick_airport(a):
                code = a.get("iata_code") or a.get("icao_code") or ""
                name = a.get("municipality") or a.get("name") or ""
                return {"code": code, "name": name}

            route = {"origin": pick_airport(origin), "destination": pick_airport(destination)}
    except Exception:
        route = None

    body = {"route": route}
    with cache_lock:
        route_cache[callsign] = (now, body)
        if len(route_cache) > 5000:
            for k in sorted(route_cache, key=lambda k: route_cache[k][0])[: len(route_cache) // 2]:
                del route_cache[k]
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

        # 【2026-10-28 新增】起降机场（按航班号）
        if path == "/api/route":
            callsign = params.get("callsign", [""])[0].strip().upper()
            if not (2 <= len(callsign) <= 10) or not callsign.isalnum():
                self._send_json({"error": "bad callsign"}, 400)
                return
            self._send_json(fetch_route(callsign))
            return

        if path != "/api/aircraft":
            self._send_json({"error": "not found"}, 404)
            return

        # 【2026-10-28 修改】lat/lon 支持逗号分隔的多个中心点，例如
        #   /api/aircraft?lat=30.6,29.2&lon=114.3,113.1&r=250
        # 前端缩小地图看大范围时会传最多 4 个点，服务端逐点查询后合并去重
        try:
            lats = [float(v) for v in params.get("lat", [""])[0].split(",") if v.strip()]
            lons = [float(v) for v in params.get("lon", [""])[0].split(",") if v.strip()]
            r = int(float(params.get("r", [""])[0]))
        except (TypeError, ValueError):
            self._send_json({"error": "bad lat/lon/r"}, 400)
            return

        if not lats or len(lats) != len(lons):
            self._send_json({"error": "bad lat/lon/r"}, 400)
            return

        points = list(zip(lats, lons))[:MAX_POINTS]
        for lat, lon in points:
            if not valid_coord(lat, lon):
                self._send_json({"error": "lat/lon out of range"}, 400)
                return

        if not MIN_RADIUS_NM <= r <= MAX_RADIUS_NM:
            self._send_json(
                {"error": "r not in %d..%d" % (MIN_RADIUS_NM, MAX_RADIUS_NM)},
                400,
            )
            return

        try:
            self._send_json(fetch_area(points, r))
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
