# 个人主页

李璇（Xuan Li）的个人学术主页：简介、论文、生活记录、网址导航和个人工具入口。

- 线上地址：<https://hlmdf.github.io>
- 技术栈：Next.js 16 + React 19 + Tailwind 4，生产环境静态导出
- 详细的项目结构、页面关系和已知限制见 [`docs/project-overview.md`](docs/project-overview.md)

## 本地运行

```bash
npm ci
npm run dev        # http://localhost:43123
```

```bash
npm run build      # 生成 out/
```

构建产物是纯静态文件，用任意静态服务器预览即可，**不要用 `npm start`**——`next start` 与 `output: "export"` 不兼容。

## 页头天气：配置高德 key

页头那个时钟旁边的位置和天气，默认走 [open-meteo](https://open-meteo.com/)：免费、不用注册，但服务器在国外，一次完整的定位到出天气要经过三个串行请求。

配上高德 key 之后会整体切到国内数据源——IP 定位和天气都是高德，走的是同一套接口，少绕两跳。没配 key 也能正常用，自动退回 open-meteo。

### 1. 注册并实名认证

打开 <https://lbs.amap.com/>，用手机号注册，然后进[控制台](https://console.amap.com/)。

**必须完成个人实名认证**，否则调用接口会返回 `INVALID_USER_KEY` 之类的一千零几种错误码，看着像 key 填错了，其实是没认证。入口在控制台左侧「账号管理」→「实名认证」。

### 2. 创建 Key

控制台 →「应用管理」→「我的应用」→ **创建新应用**（名字随便，类型选「出行」或「其他」都行）→ 在新应用右侧点 **添加 Key**。

添加时有三个字段，其中只有第二个要注意：

| 字段 | 填什么 |
| --- | --- |
| Key 名称 | 随便，比如 `personal-homepage` |
| 服务平台 | **Web服务** ← 别选「Web端(JS API)」，那个是地图 SDK 用的 |
| 域名白名单 | Web 服务不需要填 |

提交后会得到一串 32 位字符，这就是 key。

免费配额按接口分别计算，个人站一天几百次访问完全够用。

### 3. 填进项目

本地开发：在项目根目录新建 `.env.local`（已在 `.gitignore` 里，不会被提交）：

```
NEXT_PUBLIC_AMAP_KEY=你的32位key
```

改完要重启 `npm run dev` 才生效。

线上部署：仓库 **Settings → Secrets and variables → Actions → New repository secret**，名字填 `NEXT_PUBLIC_AMAP_KEY`，值填 key。工作流已经把这个 secret 传给 `npm run build`，推一次代码就会带上。

### 4. 关于 key 是公开的

`NEXT_PUBLIC_` 开头的变量会在构建时打进浏览器端的 JS 文件，**任何人打开开发者工具都能看到你的 key**。这不是配置错了，前端拿 key 就一定藏不住。

现实的后果只有一种：别人拿你的 key 刷天气接口，把当天免费的配额用光。用光之后页头会安静地退回默认状态，不会产生费用，也不会影响网站其他部分。真要藏 key 得在中间加一层服务端代理，对一个纯静态的个人站不值得。

## 部署

推 `main` 就触发 [`.github/workflows/pages.yml`](.github/workflows/pages.yml)：`npm ci` → `npm run build` → 把 `out/` 发到 GitHub Pages。

仓库的 Pages Source 需要设为 **GitHub Actions**。
