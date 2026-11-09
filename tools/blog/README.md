# 个人博客

【2026-11-09 新增】独立部署在阿里云服务器上的博客：文章（Markdown）、标签、照片、评论。
个人主页导航栏的「博客」只是入口，新标签页跳到 `https://47.103.222.155:5012/`。

和片单、访客地图等工具同一套配方：纯 Python 标准库服务监听本机 8012，Nginx 在 5012 提供 HTTPS，
systemd 守护，数据放 `/var/lib/blog`（JSON + photos/），不依赖主站构建发布。

## 文件

- `server.py`：API + 静态页面 + 照片服务，全部数据读写都在这
- `index.html`：单文件前端（列表 / 详情 / 评论 / 后台），hash 路由，自带迷你 Markdown 渲染器
- `deploy/`：nginx 配置、systemd 单元、安装脚本
- `deploy-to-aliyun.cmd`：一键打包上传安装（依赖本机已配好 `xuan-aliyun-ecs` SSH 别名）

## 本地试跑

```powershell
python server.py --host 127.0.0.1 --port 8012
```

首次启动会在 `./data/` 生成 `config.json` 和 `initial-password.txt`（初始管理密码）。
想自己定初始密码：先设环境变量 `BLOG_PASSWORD` 再启动。浏览器打开 `http://127.0.0.1:8012/`。

## 部署到服务器

双击 `deploy-to-aliyun.cmd`，或在 `tools/blog/` 下执行它。装完后到阿里云控制台
**安全组放行 TCP 5012**，再访问 `https://47.103.222.155:5012/`。

更新代码：改完文件重新跑一次 `deploy-to-aliyun.cmd` 即可，数据在 `/var/lib/blog`，不受影响。

## 使用

- 读者：打开即文章列表，可按标签筛选；文章页底部发评论（不用登录，按 IP 限流，每小时 10 条）。
- 自己：右上角「管理」登录 → 写文章（Markdown，「上传照片」会在光标处插入图片语法）/
  文章管理 / 评论管理（删垃圾评论）/ 改密码。登录令牌 7 天有效，存在浏览器 sessionStorage。

## 备份

文章、评论、照片全在 `/var/lib/blog/`，打包拷走就是完整备份：

```bash
sudo tar czf blog-backup-$(date +%F).tgz -C /var/lib blog
```
