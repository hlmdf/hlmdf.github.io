#!/usr/bin/env bash
# 在阿里云服务器上安装「我的书单」。
#
# 只新增 /opt/book-tracker 和 5004 端口，不改动 movie-tracker、filedrop、
# reminder-tool、visitor-map 的任何文件。可以重复运行：代码会被替换，
# books.json 和 config.json 不会被碰。
set -euo pipefail

test "$(id -u)" -eq 0 || { echo '请用 root 运行（ssh 的 -t 会话即可）'; exit 1; }

SRC=/tmp/book-deploy
APP_DIR=/opt/book-tracker
SERVICE=book-tracker
USER_NAME=book-tracker
PORT_LOCAL=8003
PORT_PUBLIC=5004

test -f "$SRC/server.py" || { echo "找不到 $SRC/server.py，部署包不完整"; exit 1; }
test -f "$SRC/nginx-book-tracker.conf" || { echo "找不到 nginx 配置"; exit 1; }
test -f "$SRC/book-tracker.service" || { echo "找不到 systemd 配置"; exit 1; }

echo "== 1/7 检查端口与证书 =="
if ss -lnt | awk '{print $4}' | grep -qE ":${PORT_LOCAL}$"; then
    systemctl is-active --quiet "$SERVICE" || {
        echo "本机 $PORT_LOCAL 已被其他服务占用，未做任何修改。"; exit 1; }
fi
if ss -lnt | awk '{print $4}' | grep -qE ":${PORT_PUBLIC}$"; then
    [ -e /etc/nginx/sites-enabled/book-tracker ] || {
        echo "本机 $PORT_PUBLIC 已被其他服务占用，未做任何修改。"; exit 1; }
fi
test -f /etc/nginx/ssl/ip.crt && test -f /etc/nginx/ssl/ip.key || {
    echo '没找到 /etc/nginx/ssl/ip.crt 与 ip.key，先确认现有 IP 证书路径。'; exit 1; }

echo "== 2/7 检查代码 =="
python3 - <<'PY'
from pathlib import Path
compile(Path('/tmp/book-deploy/server.py').read_text(encoding='utf-8'), 'server.py', 'exec')
PY

echo "== 3/7 准备用户与目录 =="
id "$USER_NAME" >/dev/null 2>&1 || \
    useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$USER_NAME"
install -d -o "$USER_NAME" -g "$USER_NAME" -m 750 "$APP_DIR"

echo "== 4/7 安装代码 =="
if [ -f "$APP_DIR/server.py" ]; then
    cp -p "$APP_DIR/server.py" "$APP_DIR/server.py.$(date +%Y%m%d-%H%M%S).bak"
fi
install -m 644 -o root -g root "$SRC/server.py" "$APP_DIR/server.py"

echo "== 5/7 管理密码 =="
if [ -f "$APP_DIR/config.json" ]; then
    echo "已有 config.json，保留现有密码。"
else
    echo "第一次安装，需要设一个管理密码（只写进 config.json，不会保存明文）。"
    while :; do
        read -r -s -p "  管理密码：" PASS1; echo
        [ -n "$PASS1" ] || { echo "  密码不能为空。"; continue; }
        read -r -s -p "  再输一次：" PASS2; echo
        [ "$PASS1" = "$PASS2" ] || { echo "  两次不一致，重来。"; continue; }
        break
    done
    APP_DIR="$APP_DIR" BOOK_PASSWORD="$PASS1" runuser -u "$USER_NAME" -- \
        env APP_DIR="$APP_DIR" BOOK_PASSWORD="$PASS1" python3 - <<'PY'
import os, sys
app = os.environ["APP_DIR"]
sys.path.insert(0, app)
os.chdir(app)
import server
server.load_config()
PY
    unset PASS1 PASS2
fi

echo "== 6/7 安装 systemd 服务 =="
install -m 644 "$SRC/book-tracker.service" "/etc/systemd/system/${SERVICE}.service"
systemctl daemon-reload
systemctl enable "$SERVICE" >/dev/null 2>&1
systemctl restart "$SERVICE"

echo "== 7/7 安装 Nginx 站点 =="
backup_dir=$(mktemp -d)
if [ -f /etc/nginx/sites-available/book-tracker ]; then
    cp -p /etc/nginx/sites-available/book-tracker "$backup_dir/book-tracker"
fi
install -m 644 "$SRC/nginx-book-tracker.conf" /etc/nginx/sites-available/book-tracker
ln -sfn /etc/nginx/sites-available/book-tracker /etc/nginx/sites-enabled/book-tracker

if ! nginx -t; then
    echo "Nginx 配置校验失败，正在回滚。"
    if [ -f "$backup_dir/book-tracker" ]; then
        cp -p "$backup_dir/book-tracker" /etc/nginx/sites-available/book-tracker
    else
        rm -f /etc/nginx/sites-enabled/book-tracker /etc/nginx/sites-available/book-tracker
    fi
    exit 1
fi
systemctl reload nginx

echo "== 健康检查 =="
sleep 2
if ! systemctl is-active --quiet "$SERVICE"; then
    echo "服务没起来，看日志：journalctl -u $SERVICE -n 40 --no-pager"
    exit 1
fi
if ! curl --fail --silent --max-time 5 "http://127.0.0.1:${PORT_LOCAL}/api/health" >/dev/null; then
    echo "健康检查失败，看日志：journalctl -u $SERVICE -n 40 --no-pager"
    exit 1
fi

echo
echo "装好了。"
echo "  本机：http://127.0.0.1:${PORT_LOCAL}/api/health"
echo "  对外：https://47.103.222.155:${PORT_PUBLIC}/"
echo "  数据：${APP_DIR}/books.json"
echo "  日志：journalctl -u ${SERVICE} -f"
echo
echo "主页的「我的书单」入口指向 /books/，那条页面随 GitHub Pages 发布。"
