#!/usr/bin/env bash
# Run as root from /opt/blog. Keeps articles, photos and comments in /var/lib/blog.
set -euo pipefail
cd /opt/blog
test "$(id -u)" -eq 0 || { echo '请用 sudo bash deploy/install.sh 运行'; exit 1; }
python3 -c 'import sys; assert sys.version_info >= (3, 9), "需要 Python 3.9 或更新版本"'
python3 - <<'PY'
from pathlib import Path
compile(Path('/opt/blog/server.py').read_text(encoding='utf-8'), 'server.py', 'exec')
PY
nginx -t
if ss -lnt | awk '{print $4}' | grep -qE ':5012$'; then
    if ! [ -e /etc/nginx/sites-enabled/blog ] || ! grep -q 'listen 5012 ssl;' /etc/nginx/sites-available/blog; then
        echo '端口 5012 已被其他服务占用，配置未修改。'; exit 1
    fi
fi
if ss -lnt | awk '{print $4}' | grep -qE ':8012$' && ! systemctl is-active --quiet blog; then
    echo '8012 已被其他服务占用，请先确认端口。'; exit 1
fi
test -f /etc/nginx/ssl/ip.crt && test -f /etc/nginx/ssl/ip.key || {
    echo '未找到现有 IP 的 HTTPS 证书，请先确认路径。'; exit 1;
}
id blog >/dev/null 2>&1 || useradd --system --home-dir /var/lib/blog --shell /usr/sbin/nologin blog
install -d -o blog -g blog -m 700 /var/lib/blog /var/lib/blog/photos

backup_dir=$(mktemp -d /opt/blog/nginx-backup.XXXXXX)
if [ -f /etc/nginx/sites-available/blog ]; then
    cp -p /etc/nginx/sites-available/blog "$backup_dir/blog"
fi
enabled_before=0
if [ -e /etc/nginx/sites-enabled/blog ]; then enabled_before=1; fi
install -m 644 deploy/nginx-blog.conf /etc/nginx/sites-available/blog
ln -sfn /etc/nginx/sites-available/blog /etc/nginx/sites-enabled/blog
if ! nginx -t; then
    if [ -f "$backup_dir/blog" ]; then
        cp -p "$backup_dir/blog" /etc/nginx/sites-available/blog
    else
        rm -f /etc/nginx/sites-available/blog
    fi
    if [ "$enabled_before" -eq 0 ]; then rm -f /etc/nginx/sites-enabled/blog; fi
    echo 'Nginx 检查失败，已恢复原配置。'; exit 1
fi
install -m 644 deploy/blog.service /etc/systemd/system/blog.service
systemctl daemon-reload
systemctl enable blog
systemctl restart blog
sleep 2
systemctl is-active --quiet blog
curl --fail --silent http://127.0.0.1:8012/health
echo
systemctl reload nginx
curl --fail --silent --insecure https://127.0.0.1:5012/health
echo
if command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
    firewall-cmd --permanent --add-port=5012/tcp
    firewall-cmd --reload
fi
echo '服务已启动。地址：https://47.103.222.155:5012/'
if [ -f /var/lib/blog/initial-password.txt ]; then
    echo "初始管理密码：$(cat /var/lib/blog/initial-password.txt)"
    echo '登录后台「改密码」换成自己的密码后，可以删除 /var/lib/blog/initial-password.txt'
fi
echo '若外网打不开，请在阿里云安全组放行 TCP 5012。'
