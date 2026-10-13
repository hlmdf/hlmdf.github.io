#!/usr/bin/env bash
set -euo pipefail
test "$(id -u)" -eq 0 || { echo '请用 root 或 sudo 运行'; exit 1; }
cd /tmp/personal-tools-update
systemctl cat filedrop >/dev/null
systemctl cat movie-tracker >/dev/null
test -f /opt/filedrop/server.js && test -f /opt/movie-tracker/server.py
movie_user=$(systemctl show movie-tracker --property=User --value)
movie_user=${movie_user:-root}
runuser -u "$movie_user" -- test -w /opt/movie-tracker || {
    echo '片单服务用户不能写入配置目录，需确认管理密码保存权限。'; exit 1;
}
backup=/opt/personal-tools-backup-$(date +%Y%m%d-%H%M%S)
mkdir -p "$backup/filedrop/public" "$backup/movie-tracker"
cp -p /opt/filedrop/server.js "$backup/filedrop/"
cp -p /opt/filedrop/public/index.html "$backup/filedrop/public/"
if [ -f /opt/filedrop/usage.json ]; then cp -p /opt/filedrop/usage.json "$backup/filedrop/"; fi
if [ -f /opt/filedrop/daily-quota.js ]; then cp -p /opt/filedrop/daily-quota.js "$backup/filedrop/"; fi
cp -p /opt/movie-tracker/server.py "$backup/movie-tracker/"
# Only code is installed. Uploaded files, movie data, both login configurations and Douban session stay in place.
install -m 644 filedrop/server.js /opt/filedrop/server.js
install -m 644 filedrop/daily-quota.js /opt/filedrop/daily-quota.js
install -m 644 filedrop/public/index.html /opt/filedrop/public/index.html
install -m 644 movie-tracker/server.py /opt/movie-tracker/server.py
node --check /opt/filedrop/server.js
node --check /opt/filedrop/daily-quota.js
python3 - <<'PY'
from pathlib import Path
compile(Path('/opt/movie-tracker/server.py').read_text(), 'server.py', 'exec')
PY
systemctl restart filedrop movie-tracker
sleep 2
systemctl is-active --quiet filedrop
systemctl is-active --quiet movie-tracker
curl --fail --silent http://127.0.0.1:3001/api/quota
echo
curl --fail --silent http://127.0.0.1:8001/api/health
echo
echo "两个服务已更新。原代码备份：$backup"
