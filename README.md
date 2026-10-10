# 个人主页

一份学术个人主页，栏目和 [dwangust.github.io](https://dwangust.github.io/) 同一类：关于、论文、报告，侧栏放身份和联系方式。改一份资料文件就能换成你自己的内容，再发到 GitHub Pages。

## 那个网站是不是基于 GitHub

是。`用户名.github.io` 是 GitHub Pages 的地址。

王丹老师的主页能对上三件事：

- 域名是 `dwangust.github.io`，对应 GitHub 用户 `dwangust` 的同名仓库。
- 页面响应头里的服务器是 `GitHub.com`。
- 页脚写着 Powered by Jekyll & [AcademicPages](https://github.com/academicpages/academicpages.github.io)。AcademicPages 是 [Minimal Mistakes](https://github.com/mmistakes/minimal-mistakes) 的一个分支。

页面放在公开的 Git 仓库里，GitHub 负责构建和托管，不需要自己的服务器。公开仓库可以免费使用。仓库名必须是 `你的用户名.github.io`，网站才会出现在根地址。别的仓库名会变成 `用户名.github.io/仓库名`。

## 本地运行

需要 Node.js 22。

```bash
npm install
npm run dev
```

浏览器打开 [http://localhost:43123](http://localhost:43123)。

## 改成你的内容

只改 [`content/profile.ts`](content/profile.ts)：

- 名字、学校、城市、邮箱、GitHub
- `bio` 简介，`interests` 正在关注的方向，`education` 教育经历
- `publications` 论文，`talks` 报告
- 示例条目的 `example` 改成 `false`。没有的栏目把数组留空。

PDF 放在 `public/files/`，链接写成 `/files/paper.pdf`。

顶栏可以切换中文 / 英文，以及浅色 / 深色。两种语言的句子都写在同一份资料里。

## 发布到 GitHub Pages

1. 在 GitHub 新建一个 **Public** 仓库，名字是 `你的用户名.github.io`。
2. 把这个项目推到 `main`。
3. 打开仓库 **Settings → Pages → Build and deployment**，Source 选 **GitHub Actions**。
4. [`.github/workflows/pages.yml`](.github/workflows/pages.yml) 会执行 `npm run build`，把 `out/` 发布出去。
5. 构建完成后打开 `https://你的用户名.github.io`。

如果仓库不叫 `用户名.github.io`，构建前设置：

```bash
NEXT_PUBLIC_BASE_PATH=/仓库名 npm run build
```

在 GitHub Actions 里可以把这个变量加到构建步骤的 `env`。

## 想要和参考站完全同一套模板

用 AcademicPages，主要改 Markdown，不用写这个 Next.js 项目：

1. 打开 [academicpages/academicpages.github.io](https://github.com/academicpages/academicpages.github.io)，点 **Use this template**。
2. 仓库名设为 `你的用户名.github.io`，并设为 Public。
3. 在 `_config.yml` 里写名字、学校、邮箱和 `url`。
4. 关于页是 `_pages/about.md`。论文放 `_publications/`，报告放 `_talks/`，PDF 放 `files/`，头像放 `images/`。
5. 本地预览：`bundle install`，然后 `bundle exec jekyll serve`。

更细的步骤也写在网站的「上线」页里。
