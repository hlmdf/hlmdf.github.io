# 私人提醒工具

单用户密码登录；Flask + Waitress；企业微信机器人、邮件和浏览器提醒；统一按 Asia/Shanghai 调度。
源代码放在个人主页的 tools/reminder-tool，静态导出不会包含此目录。
兼容原 data/reminders.json 和 data/settings.json，无需改字段。真实数据和登录配置不提交 Git。

## 本地运行（Windows PowerShell）

也可以直接双击 start.cmd；首次安装依赖并要求设置密码，随后启动服务。

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe setup_auth.py
$env:REMINDER_LOCAL_HTTP = '1'
.venv/Scripts/python.exe server.py
```

访问 http://127.0.0.1:8002/。密码没有长度或字符要求，只不能为空；setup_auth.py 隐藏输入，磁盘只保存密码哈希。
登录后可在“账号设置”修改密码，输入当前密码并确认新密码即可。
网页修改成功后当前设备和其他设备全部退出，需用新密码重新登录；密码会保存，重启后仍有效。
登录后保持 30 天，每次访问自动续期；关掉浏览器或重启服务后仍可保持登录。
主动退出或清除浏览器 Cookie 会要求重新登录。
仅本地 HTTP 调试设置 REMINDER_LOCAL_HTTP=1；线上不要设置。
将新版 server.py、index.html 等复制回原 reminder-tool 时保留原 data 目录。
启动新版之前，先关闭旧版 Python 进程，避免两个调度器同时发送。

## 沿用现有阿里云服务器

已有 SSH 别名 xuan-aliyun-ecs（47.103.222.155），交互式密码登录。
部署后预期地址：https://47.103.222.155:5003/
提醒工具单独使用 HTTPS 端口 5003；后端 8002 仅监听回环。阿里云安全组入方向放行 TCP 5003。
文件中转站仍使用端口 5002；更新脚本移除之前添加的提醒工具路径，分别运行两个工具。
需 Python 3.10+、python3-venv、Nginx 和当前有效的 HTTPS 配置。
脚本先检查 5003 是否空闲，备份 Nginx 配置，增加单独的 reminder-tool server。
如果已有其他程序占用 5003，脚本停止并报错。

更新可双击同目录的 deploy-to-aliyun.cmd；脚本保留已有密码，并从旧 /etc 路径迁移登录配置。

1. 本地上传不含凭据和提醒的部署包：

```powershell
scp E:\01AI\reminder-tool\reminder-tool.zip xuan-aliyun-ecs:/tmp/reminder-tool.zip
ssh xuan-aliyun-ecs
```

2. 在服务器终端安装（首次会要求设置自己的提醒工具密码）：

```bash
mkdir -p /opt/reminder-tool
python3 -m zipfile -e /tmp/reminder-tool.zip /opt/reminder-tool
cd /opt/reminder-tool
bash deploy/install.sh
```

如缺少 venv，Ubuntu/Debian 可运行 `apt-get update && apt-get install -y python3-venv` 后重试。
脚本仅启用一个服务进程，不要额外使用 flask run 或多进程 Gunicorn，否则定时任务会重复。

3. 可选：迁移原提醒和邮箱设置（传输走 SSH，已有服务器数据不会自动覆盖）。
先在服务器执行 `systemctl stop reminder-tool`；在本地执行：

```powershell
scp E:\01AI\reminder-tool\data\reminders.json E:\01AI\reminder-tool\data\settings.json xuan-aliyun-ecs:/var/lib/reminder-tool/
```

如服务器已使用过此工具，覆盖前先备份 /var/lib/reminder-tool。在服务器执行：

```bash
chown reminder-tool:reminder-tool /var/lib/reminder-tool/*.json
chmod 600 /var/lib/reminder-tool/*.json
systemctl start reminder-tool
```

4. 主页 content/profile.ts 的“提醒小助手”直接指向 https://47.103.222.155:5003/。
按原 GitHub Pages 发布流程推送 main 即可更新个人工具入口。

## 运维和边界

企业微信：登录后进入“通知渠道设置”，填入企业微信群机器人的 Webhook，保存并发送测试。
Server酱：填写 SCT 或 sctp 开头的 SendKey，支持保存、测试和定时推送。
PushPlus：填写用户 token 或消息 token，支持保存、测试和定时推送。接口接收请求后异步投递，最终结果可在 PushPlus 查看。
两种渠道均会在保存或启用提醒时检查配置；密钥不回显，留空保存会保留旧密钥。
接口依据：[Server酱](https://sct.ftqq.com/docs/getting-started/sendkey/)、[PushPlus](https://www.pushplus.plus/doc/guide/api.html)。
新建或编辑提醒时勾选“企业微信”。通知由服务器发送，关闭网页也能推送到群。
保存或启用提醒前会校验对应通知渠道配置；邮件和企业微信缺少配置时，后端也会拒绝保存或启用。
浏览器通知权限在当前设备的页面中检查；未授权会提示先授权，不会保存所选浏览器提醒。
配置完整不代表授权码或 Webhook 一定有效，实际连接请使用各渠道的“发送测试”验证。
Webhook 保存后不会回显，输入框留空保存会保留旧地址；旧配置中已有 wecom 字段会自动读取。

- 查看日志：`journalctl -u reminder-tool -n 100 --no-pager`。
- 修改登录密码：登录网页进入“账号设置”。忘记密码时，可在服务器执行 `cd /opt/reminder-tool && REMINDER_AUTH_FILE=/var/lib/reminder-tool/auth.json .venv/bin/python setup_auth.py`，然后 `chown reminder-tool:reminder-tool /var/lib/reminder-tool/auth.json && chmod 600 /var/lib/reminder-tool/auth.json && systemctl restart reminder-tool`。命令行重置会让旧会话全部失效。
- 备份 /var/lib/reminder-tool（包含 auth.json、提醒和邮箱设置）；邮箱授权码仍存于服务器文件中，需限制文件访问。API 仅返回是否配置，留空保存保留旧授权码。
- 浏览器通知需要页面保持打开、系统授权及浏览器信任的 HTTPS 证书；页面关闭或设备休眠时请使用邮件。现有 IP 证书的信任情况需在浏览器确认。
- 邮件使用 SMTP over SSL（通常 465），不支持仅 STARTTLS 的 587 配置。部署后必须发送测试邮件确认服务器可连接邮箱服务。
- 发送前持久化本分钟标记以避免重复；服务停机期间的提醒不会补发，发送失败也不会自动重试，可用“立即发送”重试。
- 登录失败 10 次后全局限制 15 分钟；单用户设计，不适合多人共用。
- 回滚：停止 reminder-tool，移除 /etc/nginx/sites-enabled/reminder-tool 链接，运行 `nginx -t && systemctl reload nginx`；保留数据目录。如需恢复旧地址，可使用 /opt/reminder-tool/nginx-backup.* 内的备份配置。

## 验证

```powershell
.venv/Scripts/python.exe -m unittest -v test_server.py
node test_frontend.cjs
```

测试使用独立临时数据，不读取真实通知配置，不发送邮件或企业微信消息。
