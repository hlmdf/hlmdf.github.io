#!/usr/bin/env bash
# Run as root from /opt/visitor-map. Keeps visit data in /var/lib/visitor-map.
set -euo pipefail
cd /opt/visitor-map
test "$(id -u)" -eq 0 || { echo '请用 sudo bash deploy/install.sh 运行'; exit 1; }
python3 -c 'import sys; assert sys.version_info >= (3, 9), "需要 Python 3.9 或更新版本"'
python3 - <<'PY'
from pathlib import Path
compile(Path('/opt/visitor-map/server.py').read_text(encoding='utf-8'), 'server.py', 'exec')
PY
nginx -t
if ss -lnt | awk '{print $4}' | grep -qE ':5010$'; then
    if ! [ -e /etc/nginx/sites-enabled/visitor-map ] || ! grep -q 'listen 5010 ssl;' /etc/nginx/sites-available/visitor-map; then
        echo '端口 5010 已被其他服务占用，配置未修改。'; exit 1
    fi
fi
if ss -lnt | awk '{print $4}' | grep -qE ':8010$' && ! systemctl is-active --quiet visitor-map; then
    echo '8010 已被其他服务占用，请先确认端口。'; exit 1
fi
test -f /etc/nginx/ssl/ip.crt && test -f /etc/nginx/ssl/ip.key || {
    echo '未找到现有 IP 的 HTTPS 证书，请先确认路径。'; exit 1;
}
id visitor-map >/dev/null 2>&1 || useradd --system --home-dir /var/lib/visitor-map --shell /usr/sbin/nologin visitor-map
install -d -o visitor-map -g visitor-map -m 700 /var/lib/visitor-map
if [ -f /opt/visitor-map/data/visits.json ] && [ ! -f /var/lib/visitor-map/visits.json ]; then
    cp -p /opt/visitor-map/data/visits.json /var/lib/visitor-map/visits.json
    chown visitor-map:visitor-map /var/lib/visitor-map/visits.json
    chmod 600 /var/lib/visitor-map/visits.json
fi

backup_dir=$(mktemp -d /opt/visitor-map/nginx-backup.XXXXXX)
if [ -f /etc/nginx/sites-available/visitor-map ]; then
    cp -p /etc/nginx/sites-available/visitor-map "$backup_dir/visitor-map"
fi
enabled_before=0
if [ -e /etc/nginx/sites-enabled/visitor-map ]; then enabled_before=1; fi
install -m 644 deploy/nginx-visitor-map.conf /etc/nginx/sites-available/visitor-map
ln -sfn /etc/nginx/sites-available/visitor-map /etc/nginx/sites-enabled/visitor-map
if ! nginx -t; then
    if [ -f "$backup_dir/visitor-map" ]; then
        cp -p "$backup_dir/visitor-map" /etc/nginx/sites-available/visitor-map
    else
        rm -f /etc/nginx/sites-available/visitor-map
    fi
    if [ "$enabled_before" -eq 0 ]; then rm -f /etc/nginx/sites-enabled/visitor-map; fi
    echo 'Nginx 检查失败，已恢复原配置。'; exit 1
fi
install -m 644 deploy/visitor-map.service /etc/systemd/system/visitor-map.service
systemctl daemon-reload
systemctl enable visitor-map
systemctl restart visitor-map
sleep 2
systemctl is-active --quiet visitor-map
curl --fail --silent http://127.0.0.1:8010/health
echo
systemctl reload nginx
curl --fail --silent --insecure https://127.0.0.1:5010/health
echo
if command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
    firewall-cmd --permanent --add-port=5010/tcp
    firewall-cmd --reload
fi
echo '服务已启动。地址：https://47.103.222.155:5010/'
echo '若外网打不开，请在阿里云安全组放行 TCP 5010。'
