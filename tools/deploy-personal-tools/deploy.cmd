@echo off
cd /d "%~dp0"
echo Enter the existing server SSH password when prompted.
scp personal-tools-update.zip xuan-aliyun-ecs:/tmp/personal-tools-update.zip
if errorlevel 1 goto failed
ssh -t xuan-aliyun-ecs "mkdir -p /tmp/personal-tools-update && python3 -m zipfile -e /tmp/personal-tools-update.zip /tmp/personal-tools-update && bash /tmp/personal-tools-update/install.sh"
if errorlevel 1 goto failed
echo Server tools updated successfully.
pause
exit /b 0
:failed
echo Update did not complete. Keep this window open to inspect the error.
pause
exit /b 1
