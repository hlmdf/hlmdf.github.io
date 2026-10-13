@echo off
cd /d "%~dp0"
echo Uploading the reminder tool. Enter your existing SSH password when asked.
scp reminder-tool.zip xuan-aliyun-ecs:/tmp/reminder-tool.zip
if errorlevel 1 goto failed
echo Installing the service. First installation also asks you to set a reminder login password.
ssh -t xuan-aliyun-ecs "mkdir -p /opt/reminder-tool && python3 -m zipfile -e /tmp/reminder-tool.zip /opt/reminder-tool && cd /opt/reminder-tool && bash deploy/install.sh"
if errorlevel 1 goto failed
echo Visit https://47.103.222.155:5003/ after opening TCP port 5003 in your security group.
pause
exit /b 0
:failed
echo Deployment did not complete. Keep this window open to inspect the error.
pause
exit /b 1
