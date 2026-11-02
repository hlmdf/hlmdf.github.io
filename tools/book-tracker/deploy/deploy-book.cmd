@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo 部署「我的书单」到阿里云 47.103.222.155
echo.
echo 全过程只新增 /opt/book-tracker 和 5004 端口，
echo 不动片单、文件中转、提醒、访客地图。
echo.

echo [1/3] 打包...
python -c "import zipfile; m={'..\\server.py':'server.py','install-book.sh':'install-book.sh','nginx-book-tracker.conf':'nginx-book-tracker.conf','book-tracker.service':'book-tracker.service'}; z=zipfile.ZipFile('book-deploy.zip','w',zipfile.ZIP_DEFLATED); [z.write(s,d) for s,d in m.items()]; z.close()"
if errorlevel 1 goto fail

echo [2/3] 上传...
scp book-deploy.zip xuan-aliyun-ecs:/tmp/book-deploy.zip
if errorlevel 1 goto fail

echo [3/3] 安装中（先输服务器密码，再设书单管理密码）...
ssh -t xuan-aliyun-ecs "rm -rf /tmp/book-deploy && mkdir -p /tmp/book-deploy && python3 -m zipfile -e /tmp/book-deploy.zip /tmp/book-deploy && bash /tmp/book-deploy/install-book.sh"
if errorlevel 1 goto fail

del book-deploy.zip >nul 2>&1
echo.
echo 完成。打开 https://47.103.222.155:5004/ 看看。
pause
exit /b 0

:fail
echo.
echo 部署失败，上面有具体原因。
pause
exit /b 1
