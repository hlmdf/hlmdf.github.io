#!/usr/bin/env bash
# 部署 PDF 工具箱后端到 /opt/pdf-toolkit。可重复执行：
# 依赖已装则跳过，.env 和 .venv 不会被覆盖。
set -euo pipefail
cd /opt/pdf-toolkit
[ "$(id -u)" -eq 0 ] || { echo '请用 sudo bash deploy/install.sh 运行'; exit 1; }

need=()
for cmd in soffice gs qpdf pdftotext pdftoppm tesseract; do
    command -v "$cmd" >/dev/null 2>&1 || need+=("$cmd")
done

if [ ${#need[@]} -gt 0 ]; then
    echo "缺少命令：${need[*]}，开始安装系统依赖（首次较慢，约 1GB）…"
    if command -v apt-get >/dev/null 2>&1; then
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y --no-install-recommends \
            libreoffice-writer libreoffice-calc libreoffice-impress fonts-noto-cjk \
            ghostscript qpdf poppler-utils tesseract-ocr tesseract-ocr-chi-sim \
            libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libcairo2 \
            libgdk-pixbuf-2.0-0 shared-mime-info python3-venv
    elif command -v dnf >/dev/null 2>&1; then
        dnf install -y libreoffice-writer libreoffice-calc libreoffice-impress \
            google-noto-sans-cjk-fonts ghostscript qpdf poppler-utils tesseract \
            tesseract-langpack-chi_sim pango harfbuzz cairo gdk-pixbuf2 \
            shared-mime-info python3 python3-pip
    else
        echo '未识别的包管理器，请手动安装 LibreOffice / Ghostscript / qpdf / poppler / Tesseract 后重试。'
        exit 1
    fi
fi

[ -d .venv ] || python3 -m venv .venv
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -r requirements.txt

if [ ! -f .env ]; then
    token=$(python3 -c 'import secrets; print(secrets.token_hex(24))')
    code=$(python3 -c 'import secrets; print(secrets.token_hex(4))')
    cat > .env <<EOF
API_TOKEN=$token
SIGNUP_CODE=$code
ALLOWED_ORIGINS=https://hlmdf.github.io
MAX_MB=100
EOF
    chmod 600 .env
    echo "已生成 API_TOKEN：$token"
    echo "已生成注册码 SIGNUP_CODE：$code"
    echo '把注册码告诉要用的人；游客不登录也能用，每天有免费次数。'
fi

if ! grep -q '^SIGNUP_CODE=' .env; then
    code=$(python3 -c 'import secrets; print(secrets.token_hex(4))')
    echo "SIGNUP_CODE=$code" >> .env
    echo "已补上注册码 SIGNUP_CODE：$code"
fi

id pdftool >/dev/null 2>&1 || useradd --system --home-dir /var/lib/pdf-toolkit --shell /usr/sbin/nologin pdftool
install -d -o pdftool -g pdftool -m 700 /var/lib/pdf-toolkit

test -f /etc/nginx/ssl/ip.crt && test -f /etc/nginx/ssl/ip.key || {
    echo '未找到 /etc/nginx/ssl/ip.crt 或 ip.key，无法启用 HTTPS。'
    exit 1
}

backup_dir=$(mktemp -d)
if [ -f /etc/nginx/sites-available/pdf-toolkit ]; then
    cp -p /etc/nginx/sites-available/pdf-toolkit "$backup_dir/conf"
fi
enabled_before=0
if [ -e /etc/nginx/sites-enabled/pdf-toolkit ]; then enabled_before=1; fi

install -m 644 deploy/nginx-pdf.conf /etc/nginx/sites-available/pdf-toolkit
ln -sfn /etc/nginx/sites-available/pdf-toolkit /etc/nginx/sites-enabled/pdf-toolkit
if ! nginx -t; then
    if [ -f "$backup_dir/conf" ]; then
        cp -p "$backup_dir/conf" /etc/nginx/sites-available/pdf-toolkit
    else
        rm -f /etc/nginx/sites-available/pdf-toolkit
    fi
    if [ "$enabled_before" -eq 0 ]; then rm -f /etc/nginx/sites-enabled/pdf-toolkit; fi
    echo 'Nginx 配置检查失败，已回滚。'
    exit 1
fi

install -m 644 deploy/pdf-toolkit.service /etc/systemd/system/pdf-toolkit.service
systemctl daemon-reload
systemctl enable pdf-toolkit >/dev/null 2>&1 || true
systemctl restart pdf-toolkit
sleep 3
if ! systemctl is-active --quiet pdf-toolkit; then
    journalctl -u pdf-toolkit -n 30 --no-pager
    exit 1
fi

curl --fail --silent http://127.0.0.1:8013/api/health
echo
systemctl reload nginx
curl --fail --silent --insecure https://127.0.0.1:5013/api/health
echo

if command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
    firewall-cmd --permanent --add-port=5013/tcp
    firewall-cmd --reload
fi

echo '服务已启动：https://47.103.222.155:5013/api/health'
echo '若外网打不开，请在阿里云安全组放行 TCP 5013。'
