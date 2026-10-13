@echo off
chcp 65001 >nul
cd /d "%~dp0"
scp inspect_douban_form.py xuan-aliyun-ecs:/opt/movie-tracker/inspect_douban_form.py
if errorlevel 1 goto done
ssh -t xuan-aliyun-ecs "cd /opt/movie-tracker && python3 inspect_douban_form.py"
:done
pause
