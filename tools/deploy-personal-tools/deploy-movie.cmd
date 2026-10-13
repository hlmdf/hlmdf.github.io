@echo off
cd /d "%~dp0"
echo Enter the existing server SSH password when prompted.
scp movie-review-update.zip xuan-aliyun-ecs:/tmp/movie-review-update.zip
if errorlevel 1 goto failed
ssh -t xuan-aliyun-ecs "mkdir -p /tmp/movie-review-update && python3 -m zipfile -e /tmp/movie-review-update.zip /tmp/movie-review-update && bash /tmp/movie-review-update/install-movie.sh"
if errorlevel 1 goto failed
echo Movie tracker updated successfully.
pause
exit /b 0
:failed
echo Update did not complete. Keep this window open to inspect the error.
pause
exit /b 1
