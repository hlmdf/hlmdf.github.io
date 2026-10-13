#!/usr/bin/env bash
set -euo pipefail
test "$(id -u)" -eq 0
cd /tmp/movie-review-update
systemctl cat movie-tracker >/dev/null
test -f /opt/movie-tracker/server.py
python3 - <<'PY'
from pathlib import Path
compile(Path('server.py').read_text(), 'server.py', 'exec')
PY
backup=/opt/movie-tracker-server-$(date +%Y%m%d-%H%M%S).py.bak
cp -p /opt/movie-tracker/server.py "$backup"
install -m 644 server.py /opt/movie-tracker/server.py
if ! systemctl restart movie-tracker; then
    cp -p "$backup" /opt/movie-tracker/server.py
    systemctl restart movie-tracker
    echo 'Update failed; previous code restored.'
    exit 1
fi
sleep 2
if ! systemctl is-active --quiet movie-tracker || ! curl --fail --silent http://127.0.0.1:8001/api/health; then
    cp -p "$backup" /opt/movie-tracker/server.py
    systemctl restart movie-tracker
    echo 'Health check failed; previous code restored.'
    exit 1
fi
echo
echo "Movie tracker updated successfully. Backup: $backup"
