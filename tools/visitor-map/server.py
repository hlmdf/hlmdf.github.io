# -*- coding: utf-8 -*-
"""
【2026-10-16 新增】访客地图后端服务

放在你自己有公网 IP 的服务器上运行（本项目部署在 47.103.222.155）。
- 纯 Python 标准库，不需要 pip install 任何东西
- 职责：记录访客上报的位置点、累计访问次数、对外提供统计数据
- 前端页面（https://hlmdf.github.io）通过 HTTPS 跨域调用本服务

接口：
  POST /api/visit   记录一次访问。请求体可带 {"lat":37.77,"lng":-122.42,"city":"San Francisco","country":"US"}
  GET  /api/stats   返回 {"total":123,"unique":45,"updated":1697000000,"points":[...]}

服务器上用 deploy/install.sh 安装：Nginx 在 5010 提供 HTTPS，本进程只监听 127.0.0.1:8010。
本地试跑：
    python server.py --host 127.0.0.1 --port 8010
"""

import argparse
import hashlib
import json
import os
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("VISITOR_DATA_DIR") or os.path.join(BASE_DIR, "data")
STORAGE = os.path.join(DATA_DIR, "visits.json")

# 同一个 IP 在这个时间窗口（秒）内重复访问只算一次，避免刷新页面把次数刷爆
DEDUPE_SECONDS = 1800
# seen 表里超过这个天数的记录会被清掉，"独立访客"即 seen 表里的条目数
SEEN_TTL_SECONDS = 30 * 24 * 3600
# 地图上最多保留多少个点
MAX_POINTS = 1000
# 单次返回给前端的点数上限
RETURN_POINTS = 500
# 对 IP 做哈希用的固定盐，不存明文 IP（隐私考虑）
IP_SALT = "hlmdf-visitor-map-2026"

os.makedirs(DATA_DIR, exist_ok=True)
data_lock = threading.Lock()

EMPTY_STORE = {"total": 0, "seen": {}, "points": [], "started": int(time.time())}


# ---------------- 存储 ----------------

def load_store():
    if not os.path.exists(STORAGE):
        return dict(EMPTY_STORE, seen={}, points=[])
    try:
        with open(STORAGE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return dict(EMPTY_STORE, seen={}, points=[])
    if not isinstance(data.get("seen"), dict):
        data["seen"] = {}
    if not isinstance(data.get("points"), list):
        data["points"] = []
    data.setdefault("total", 0)
    data.setdefault("started", int(time.time()))
    return data


def save_store(store):
    tmp = STORAGE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False)
    os.replace(tmp, STORAGE)


def prune(store, now):
    """清掉过期的 seen 记录，并限制 points 数量"""
    cutoff = now - SEEN_TTL_SECONDS
    store["seen"] = {h: ts for h, ts in store["seen"].items() if ts >= cutoff}
    if len(store["points"]) > MAX_POINTS:
        store["points"] = store["points"][-MAX_POINTS:]


def hash_ip(ip):
    return hashlib.sha256((IP_SALT + ip).encode("utf-8")).hexdigest()[:16]


def valid_coord(lat, lng):
    if isinstance(lat, bool) or isinstance(lng, bool):
        return False
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return False
    return -90 <= float(lat) <= 90 and -180 <= float(lng) <= 180


def stats_view(store):
    points = store["points"][-RETURN_POINTS:]
    return {
        "total": store["total"],
        "unique": len(store["seen"]),
        "updated": int(time.time()),
        "points": points,
    }


def record_visit(ip, payload):
    """记一次访问，返回最新的统计数据"""
    now = int(time.time())
    h = hash_ip(ip)
    with data_lock:
        store = load_store()
        prune(store, now)

        counted = now - store["seen"].get(h, 0) >= DEDUPE_SECONDS
        if counted:
            store["total"] += 1
            lat, lng = payload.get("lat"), payload.get("lng")
            if valid_coord(lat, lng):
                store["points"].append({
                    "lat": round(float(lat), 4),
                    "lng": round(float(lng), 4),
                    "city": str(payload.get("city") or "")[:64],
                    "country": str(payload.get("country") or "")[:64],
                    "ts": now,
                })
        store["seen"][h] = now

        save_store(store)
        return stats_view(store)


def read_stats():
    with data_lock:
        store = load_store()
        prune(store, int(time.time()))
        return stats_view(store)


# ---------------- HTTP 服务 ----------------

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "VisitorMap/1.0"

    def log_message(self, fmt, *args):
        pass  # 不打印访问日志，避免刷屏

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
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
        # 只相信本机反代写上的地址。公网直连时忽略客户端自带的转发头，避免伪造 IP 刷次数。
        peer = self.client_address[0]
        if peer in ("127.0.0.1", "::1"):
            for header in ("X-Real-IP", "X-Forwarded-For"):
                value = self.headers.get(header)
                if value:
                    return value.split(",")[0].strip()
        return peer

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return {}
        if length <= 0 or length > 64 * 1024:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path == "/api/stats":
            self._send_json(read_stats())
        elif path in ("/", "/health"):
            self._send_json({"ok": True})
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")
        if path == "/api/visit":
            self._send_json(record_visit(self._client_ip(), self._read_json()))
        else:
            self._send_json({"error": "not found"}, 404)


def main():
    parser = argparse.ArgumentParser(description="访客地图后端服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=5010, help="监听端口")
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

    print("访客地图服务已启动：%s://%s:%d" % (scheme, args.host, args.port))
    print("  记录访问 POST %s://%s:%d/api/visit" % (scheme, args.host, args.port))
    print("  读取统计 GET  %s://%s:%d/api/stats" % (scheme, args.host, args.port))
    print("按 Ctrl+C 停止。")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")


if __name__ == "__main__":
    main()
