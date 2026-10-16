@echo off
cd /d "%~dp0"
echo Uploading the visitor map. Enter your existing SSH password when asked.
python -c "import zipfile; from pathlib import Path; root=Path('.').resolve(); z=zipfile.ZipFile('visitor-map.zip','w',zipfile.ZIP_DEFLATED); files=['server.py','deploy/install.sh','deploy/nginx-visitor-map.conf','deploy/visitor-map.service']; [z.write(root/name, name) for name in files]; z.close()"
if errorlevel 1 goto failed
scp visitor-map.zip xuan-aliyun-ecs:/tmp/visitor-map.zip
if errorlevel 1 goto failed
ssh -t xuan-aliyun-ecs "mkdir -p /opt/visitor-map && python3 -m zipfile -e /tmp/visitor-map.zip /opt/visitor-map && cd /opt/visitor-map && bash deploy/install.sh"
if errorlevel 1 goto failed
echo Visit https://47.103.222.155:5010/health after opening TCP port 5010 in the Aliyun security group.
exit /b 0
:failed
echo Deployment did not complete.
exit /b 1
