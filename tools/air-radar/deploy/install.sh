#!/usr/bin/env bash
# Run as root from /opt/air-radar.
set -euo pipefail
cd /opt/air-radar
test "$(id -u)" -eq 0 || { echo '请用 sudo bash deploy/install.sh 运行'; exit 1; }
python3 -c 'import sys; assert sys.version_info >= (3, 9), "需要 Python 3.9 或更新版本"'
python3 - <<'PY'
from pathlib import Path
compile(Path('/opt/air-radar/server.py').read_text(encoding='utf-8'), 'server.py', 'exec')
PY
nginx -t
if ss -lnt | awk '{print $4}' | grep -qE ':5011$'; then
    if ! [ -e /etc/nginx/sites-enabled/air-radar ] || ! grep -q 'listen 5011 ssl;' /etc/nginx/sites-available/air-radar; then
        echo '端口 5011 已被其他服务占用，配置未修改。'; exit 1
    fi
fi
if ss -lnt | awk '{print $4}' | grep -qE ':8011$' && ! systemctl is-active --quiet air-radar; then
    echo '8011 已被其他服务占用，请先确认端口。'; exit 1
fi
test -f /etc/nginx/ssl/ip.crt && test -f /etc/nginx/ssl/ip.key || {
    echo '未找到现有 IP 的 HTTPS 证书，请先确认路径。'; exit 1;
}
id air-radar >/dev/null 2>&1 || useradd --system --shell /usr/sbin/nologin air-radar

backup_dir=$(mktemp -d /opt/air-radar/nginx-backup.XXXXXX)
if [ -f /etc/nginx/sites-available/air-radar ]; then
    cp -p /etc/nginx/sites-available/air-radar "$backup_dir/air-radar"
fi
enabled_before=0
if [ -e /etc/nginx/sites-enabled/air-radar ]; then enabled_before=1; fi
install -m 644 deploy/nginx-air-radar.conf /etc/nginx/sites-available/air-radar
ln -sfn /etc/nginx/sites-available/air-radar /etc/nginx/sites-enabled/air-radar
if ! nginx -t; then
    if [ -f "$backup_dir/air-radar" ]; then
        cp -p "$backup_dir/air-radar" /etc/nginx/sites-available/air-radar
    else
        rm -f /etc/nginx/sites-available/air-radar
    fi
    if [ "$enabled_before" -eq 0 ]; then rm -f /etc/nginx/sites-enabled/air-radar; fi
    echo 'Nginx 检查失败，已恢复原配置。'; exit 1
fi
install -m 644 deploy/air-radar.service /etc/systemd/system/air-radar.service
systemctl daemon-reload
systemctl enable air-radar
systemctl restart air-radar
sleep 2
systemctl is-active --quiet air-radar
curl --fail --silent http://127.0.0.1:8011/health
echo
systemctl reload nginx
curl --fail --silent --insecure https://127.0.0.1:5011/health
echo
if command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
    firewall-cmd --permanent --add-port=5011/tcp
    firewall-cmd --reload
fi
echo '服务已启动。地址：https://47.103.222.155:5011/'
echo '若外网打不开，请在阿里云安全组放行 TCP 5011。'
