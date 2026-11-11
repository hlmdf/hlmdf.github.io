@echo off
cd /d "%~dp0"
echo Uploading the PDF toolkit API. Enter your SSH password when asked.
python -c "import zipfile; from pathlib import Path; root=Path('.').resolve(); z=zipfile.ZipFile('pdf-toolkit.zip','w',zipfile.ZIP_DEFLATED); files=['main.py','requirements.txt','deploy/install.sh','deploy/nginx-pdf.conf','deploy/pdf-toolkit.service']; [z.write(root/name, name) for name in files]; z.close()"
if errorlevel 1 goto failed
scp pdf-toolkit.zip xuan-aliyun-ecs:/tmp/pdf-toolkit.zip
if errorlevel 1 goto failed
ssh -t xuan-aliyun-ecs "mkdir -p /opt/pdf-toolkit && python3 -m zipfile -e /tmp/pdf-toolkit.zip /opt/pdf-toolkit && cd /opt/pdf-toolkit && bash deploy/install.sh"
if errorlevel 1 goto failed
echo Visit https://47.103.222.155:5013/api/health after opening TCP port 5013 in the Aliyun security group.
exit /b 0
:failed
echo Deployment did not complete.
exit /b 1
