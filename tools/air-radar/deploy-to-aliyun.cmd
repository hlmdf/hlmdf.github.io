@echo off
cd /d "%~dp0"
echo Uploading the air radar proxy. Enter your existing SSH password when asked.
python -c "import zipfile; from pathlib import Path; root=Path('.').resolve(); z=zipfile.ZipFile('air-radar.zip','w',zipfile.ZIP_DEFLATED); files=['server.py','deploy/install.sh','deploy/nginx-air-radar.conf','deploy/air-radar.service']; [z.write(root/name, name) for name in files]; z.close()"
if errorlevel 1 goto failed
scp air-radar.zip xuan-aliyun-ecs:/tmp/air-radar.zip
if errorlevel 1 goto failed
ssh -t xuan-aliyun-ecs "mkdir -p /opt/air-radar && python3 -m zipfile -e /tmp/air-radar.zip /opt/air-radar && cd /opt/air-radar && bash deploy/install.sh"
if errorlevel 1 goto failed
echo Visit https://47.103.222.155:5011/health after opening TCP port 5011 in the Aliyun security group.
exit /b 0
:failed
echo Deployment did not complete.
exit /b 1
