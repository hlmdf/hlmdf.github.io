@echo off
cd /d "%~dp0"
echo.
echo Deploying the book list to 47.103.222.155
echo.
echo This only creates /opt/book-tracker and port 5004.
echo Movies, file drop, reminders and the visitor map are untouched.
echo.

echo [1/3] Packing...
python -c "import zipfile; m={'..\\server.py':'server.py','install-book.sh':'install-book.sh','nginx-book-tracker.conf':'nginx-book-tracker.conf','book-tracker.service':'book-tracker.service'}; z=zipfile.ZipFile('book-deploy.zip','w',zipfile.ZIP_DEFLATED); [z.write(s,d) for s,d in m.items()]; z.close()"
if errorlevel 1 goto fail

echo [2/3] Uploading...
scp book-deploy.zip xuan-aliyun-ecs:/tmp/book-deploy.zip
if errorlevel 1 goto fail

echo [3/3] Installing...
echo You will be asked for the server root password twice,
echo then for a new book-list admin password.
ssh -t xuan-aliyun-ecs "rm -rf /tmp/book-deploy && mkdir -p /tmp/book-deploy && python3 -m zipfile -e /tmp/book-deploy.zip /tmp/book-deploy && bash /tmp/book-deploy/install-book.sh"
if errorlevel 1 goto fail

del book-deploy.zip >nul 2>&1
echo.
echo Done. Open https://47.103.222.155:5004/
pause
exit /b 0

:fail
echo.
echo Deployment failed. See the message above; nothing was half-applied.
pause
exit /b 1
