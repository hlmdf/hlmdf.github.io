# 我的书单

和「我的片单」是同一套东西换了个对象：前端 `public/books/index.html` 随主站发到 GitHub Pages，后端 `server.py` 单独跑在一台服务器上。

## 本地跑

后端，默认监听 `127.0.0.1:8003`：

```bash
BOOK_PASSWORD=你的管理密码 python server.py
```

看前端：主站 `npm run dev`，打开 <http://localhost:43123/books/>。前端在 localhost 上会自动请求 `http://127.0.0.1:8003` 的接口，不用改配置。

线上由 Nginx 用 HTTPS `5004` 转发到回环 `8003`。

## 数据放在哪

| 文件 | 内容 |
| --- | --- |
| `books.json` | 条目本身 |
| `config.json` | 管理密码哈希、令牌密钥 |
| `douban_session.json` | 豆瓣登录状态 |

三个都不进 Git，也不该进部署包。

## 部署到阿里云

**先确认阿里云控制台的安全组放行了 5004/TCP**，否则脚本装完也是外网连不上。现有服务占用的端口是 8000（片单）、5002（文件中转）、5003（提醒）、5010（访客地图），书单用 5004，互不冲突。

`deploy/` 下是同款流程，双击 `deploy-book.cmd`：

1. 本地打 zip → `scp` 上传 → 服务器解压后跑 `install-book.sh`
2. 中途输两次密码：服务器 root 密码、书单管理密码

`install-book.sh` 只做这些，不碰其他服务：

- 建系统用户 `book-tracker` 和目录 `/opt/book-tracker`
- 装 `server.py`，首次生成 `config.json`（密码哈希，权限 0600）
- 注册 `book-tracker.service`，跑在 `127.0.0.1:8003`
- 加 Nginx 站点，HTTPS `5004` → `8003`，复用现有 `/etc/nginx/ssl/ip.*` 证书
- 端口冲突、Nginx 校验失败都会中止并回滚

数据是 `/opt/book-tracker/books.json`，和片单的 `movies.json` 两份文件，互不影响。重复运行只会替换代码，不会碰数据。

## 和片单不一样的地方

- 状态是 **读过 / 在读 / 想读**，没有「电影 / 电视剧」这种分类维度
- 作者、译者、出版社分开存，出版社是数组（一本可能有联合出版）
- 搜索走豆瓣读书的 `rexxar/api/v2/search/book`，**搜索结果本身就带评分和简介**，不用像电影那样再逐条查一次详情
- 详情接口是 `rexxar/api/v2/book/{id}`，字段和电影不同：出版社叫 `press`，出版年月叫 `pubdate` 且是数组，评分在 `rating.value`
- 副标题解析要额外处理国籍：豆瓣会把「[哥伦比亚]」单独切成一段，得先粘回作者名，否则国籍会被当成作者、作者被当成译者

## 豆瓣导入

抓的是网页版收藏页：`book.douban.com/people/{uid}/collect|do|wish`（读过 / 在读 / 想读）。豆瓣的 rexxar 收藏接口对图书返回 404，网页版反而稳。

卡片结构是 `<li class="subject-item">`，书名在 `<h2><a title="...">`，出版信息在 `<div class="pub">`，格式为「作者 / 译者 / 出版社 / 年份 / 价格」——译者和价格可能没有，所以解析时以「含年份的那一段」为锚点往前推，而不是按固定下标取。

每本书还会再查一次详情接口 `rexxar/api/v2/book/{id}` 补豆瓣评分；详情被限流时用 `pub` 里的信息兜底，不会空着。

## 还没做的

- **测试脚本**。片单那边的几个测试文件全是按电影字段写的，没有搬过来，这个目录下现在只剩 `test_password.py`。
