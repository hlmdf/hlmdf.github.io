@echo off
cd /d "%~dp0"
echo Uploading the blog service. Enter your existing SSH password when asked.
python -c "import zipfile; from pathlib import Path; root=Path('.').resolve(); z=zipfile.ZipFile('blog.zip','w',zipfile.ZIP_DEFLATED); files=['server.py','index.html','deploy/install.sh','deploy/nginx-blog.conf','deploy/blog.service']; [z.write(root/name, name) for name in files]; z.close()"
if errorlevel 1 goto failed
scp blog.zip xuan-aliyun-ecs:/tmp/blog.zip
if errorlevel 1 goto failed
ssh -t xuan-aliyun-ecs "mkdir -p /opt/blog && python3 -m zipfile -e /tmp/blog.zip /opt/blog && cd /opt/blog && bash deploy/install.sh"
if errorlevel 1 goto failed
echo Visit https://47.103.222.155:5012/health after opening TCP port 5012 in the Aliyun security group.
exit /b 0
:failed
echo Deployment did not complete.
exit /b 1
