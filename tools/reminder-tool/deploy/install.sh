#!/usr/bin/env bash
# Run as root from /opt/reminder-tool; optional --reset-password asks for a new password.
set -euo pipefail
cd /opt/reminder-tool
test "$(id -u)" -eq 0 || { echo '请用 sudo bash deploy/install.sh 运行'; exit 1; }
python3 -c 'import sys; assert sys.version_info >= (3, 10), "需要 Python 3.10 或更新版本"'
nginx -t
# A previously configured reminder-tool listener can reuse its own port.
if ss -lnt | awk '{print $4}' | grep -qE ':5003$'; then
    if ! [ -e /etc/nginx/sites-enabled/reminder-tool ] || ! grep -q 'listen 5003 ssl;' /etc/nginx/sites-available/reminder-tool; then
        echo '端口 5003 已被其他服务占用，配置未修改。'; exit 1
    fi
fi
if ss -lnt | awk '{print $4}' | grep -qE ':8002$' && ! systemctl is-active --quiet reminder-tool; then
    echo '8002 已被其他服务占用，请先确认端口。'; exit 1
fi
test -f /etc/nginx/ssl/ip.crt && test -f /etc/nginx/ssl/ip.key || {
    echo '未找到现有 IP 的 HTTPS 证书，请先确认路径。'; exit 1;
}
python3 -m venv .venv || { echo '请先安装 python3-venv，再重新运行本脚本。'; exit 1; }
.venv/bin/python -m pip install -r requirements.txt
id reminder-tool >/dev/null 2>&1 || useradd --system --home-dir /var/lib/reminder-tool --shell /usr/sbin/nologin reminder-tool
install -d -o reminder-tool -g reminder-tool -m 700 /var/lib/reminder-tool
# Move the active credential copy into the private, service-writable data directory.
if [ ! -f /var/lib/reminder-tool/auth.json ] && [ -f /etc/reminder-tool/auth.json ]; then
    cp /etc/reminder-tool/auth.json /var/lib/reminder-tool/auth.json
fi
if [ ! -f /var/lib/reminder-tool/auth.json ] || [ "${1:-}" = '--reset-password' ]; then
    REMINDER_AUTH_FILE=/var/lib/reminder-tool/auth.json .venv/bin/python setup_auth.py
fi
chown reminder-tool:reminder-tool /var/lib/reminder-tool/auth.json
chmod 600 /var/lib/reminder-tool/auth.json

backup_dir=$(mktemp -d /opt/reminder-tool/nginx-backup.XXXXXX)
for name in filedrop reminder-tool; do
    if [ -f "/etc/nginx/sites-available/$name" ]; then
        cp -p "/etc/nginx/sites-available/$name" "$backup_dir/$name"
    fi
done
enabled_before=0
if [ -e /etc/nginx/sites-enabled/reminder-tool ]; then enabled_before=1; fi
# Remove only the scoped include previously added to the other tool's server.
python3 - <<'PY'
from pathlib import Path
import re
path = Path('/etc/nginx/sites-available/filedrop')
if path.exists():
    text = path.read_text()
    revised = re.sub(r'(?m)^\s*include /etc/nginx/snippets/reminder-tool\.conf;[^\S\n]*\n?', '', text)
    if revised != text:
        path.write_text(revised)
PY
install -m 644 deploy/nginx-reminder.conf /etc/nginx/sites-available/reminder-tool
ln -sfn /etc/nginx/sites-available/reminder-tool /etc/nginx/sites-enabled/reminder-tool
if ! nginx -t; then
    if [ -f "$backup_dir/filedrop" ]; then cp -p "$backup_dir/filedrop" /etc/nginx/sites-available/filedrop; fi
    if [ -f "$backup_dir/reminder-tool" ]; then
        cp -p "$backup_dir/reminder-tool" /etc/nginx/sites-available/reminder-tool
    else
        rm -f /etc/nginx/sites-available/reminder-tool
    fi
    if [ "$enabled_before" -eq 0 ]; then rm -f /etc/nginx/sites-enabled/reminder-tool; fi
    echo 'Nginx 检查失败，已恢复原配置。'; exit 1
fi
install -m 644 deploy/reminder-tool.service /etc/systemd/system/reminder-tool.service
systemctl daemon-reload
systemctl enable reminder-tool
systemctl restart reminder-tool
sleep 2
systemctl is-active --quiet reminder-tool
curl --fail --silent http://127.0.0.1:8002/api/session >/dev/null
systemctl reload nginx
curl --fail --silent --insecure https://127.0.0.1:5003/api/session >/dev/null
echo '服务已启动。新地址：https://47.103.222.155:5003/'
echo '请在阿里云安全组放行 TCP 5003；原文件中转站继续使用 5002。'
