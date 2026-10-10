"use client";

import { useSite } from "@/components/site-provider";
import { PageHeader } from "@/components/page-header";

type Cell = string | { zh: string; en: string };

const comparison: { label: Cell; reference: Cell; here: Cell }[] = [
  {
    label: { zh: "托管", en: "Host" },
    reference: "GitHub Pages",
    here: "GitHub Pages",
  },
  {
    label: { zh: "地址", en: "Address" },
    reference: "用户名.github.io",
    here: "用户名.github.io",
  },
  {
    label: { zh: "怎么生成页面", en: "How pages are built" },
    reference: "Jekyll + AcademicPages",
    here: "Next.js",
  },
  {
    label: { zh: "改内容的地方", en: "Where you edit" },
    reference: { zh: "Markdown 和 YAML", en: "Markdown and YAML" },
    here: "content/profile.ts",
  },
];

function cell(value: Cell, lang: "zh" | "en") {
  return typeof value === "string" ? value : value[lang];
}

function Step({
  index,
  title,
  body,
}: {
  index: number;
  title: string;
  body: string;
}) {
  return (
    <li className="grid grid-cols-[2rem_minmax(0,1fr)] gap-3">
      <span className="flex size-8 items-center justify-center rounded-full bg-primary text-sm text-primary-foreground">
        {index}
      </span>
      <div>
        <p className="font-medium leading-8">{title}</p>
        <p className="text-sm leading-6 text-muted-foreground">{body}</p>
      </div>
    </li>
  );
}

export function PublishView() {
  const { lang } = useSite();
  const zh = lang === "zh";

  const academicSteps = zh
    ? [
        {
          title: "准备一个 GitHub 账号",
          body: "注册后要验证邮箱。GitHub Pages 用这个账号名当成网站地址。",
        },
        {
          title: "用 AcademicPages 当模板建仓库",
          body: "打开 academicpages/academicpages.github.io，点 Use this template。仓库名必须是「你的用户名.github.io」，并设为 Public。",
        },
        {
          title: "改站点和关于页",
          body: "在 _config.yml 里写名字、学校、邮箱，并把 url 设成 https://你的用户名.github.io。关于页在 _pages/about.md。头像放进 images/。",
        },
        {
          title: "加论文和报告",
          body: "每篇论文一个 Markdown 文件，放在 _publications/。报告放在 _talks/。PDF 放在 files/。",
        },
        {
          title: "等 GitHub 构建",
          body: "提交后打开仓库 Settings → Pages，看构建是否完成。完成后访问 https://你的用户名.github.io。本地预览用 bundle install，然后 bundle exec jekyll serve。",
        },
      ]
    : [
        {
          title: "Create a GitHub account",
          body: "Confirm the email address. GitHub Pages uses the account name as the site address.",
        },
        {
          title: "Start a repository from AcademicPages",
          body: "Open academicpages/academicpages.github.io and choose Use this template. Name the repository exactly your-username.github.io and make it public.",
        },
        {
          title: "Edit the site config and about page",
          body: "Set your name, school, and email in _config.yml, and set url to https://your-username.github.io. The about page is _pages/about.md. Put a portrait in images/.",
        },
        {
          title: "Add papers and talks",
          body: "One Markdown file per paper in _publications/, and talks in _talks/. Put PDFs in files/.",
        },
        {
          title: "Wait for GitHub to build",
          body: "After you push, open Settings → Pages and wait for the build. The site is then at https://your-username.github.io. Locally, run bundle install and then bundle exec jekyll serve.",
        },
      ];

  const thisSiteSteps = zh
    ? [
        {
          title: "先改内容",
          body: "打开 content/profile.ts，换成你的名字、学校、邮箱、教育和作品。示例条目的 example 改成 false。",
        },
        {
          title: "在本地看效果",
          body: "运行 npm install，再运行 npm run dev，用浏览器打开 http://localhost:43123。",
        },
        {
          title: "推到同名仓库",
          body: "新建公开仓库，名字是「你的用户名.github.io」，把这个项目推到 main 分支。",
        },
        {
          title: "打开 GitHub Actions 发布",
          body: "仓库 Settings → Pages → Build and deployment，Source 选 GitHub Actions。已有的工作流会执行 npm run build，并把 out 目录发布出去。",
        },
      ]
    : [
        {
          title: "Edit the content first",
          body: "Open content/profile.ts and replace the name, school, email, education, and work. Set example to false on real entries.",
        },
        {
          title: "Preview locally",
          body: "Run npm install, then npm run dev, and open http://localhost:43123.",
        },
        {
          title: "Push to the matching repository",
          body: "Create a public repository named your-username.github.io and push this project to main.",
        },
        {
          title: "Publish with GitHub Actions",
          body: "In Settings → Pages → Build and deployment, set Source to GitHub Actions. The workflow runs npm run build and publishes the out directory.",
        },
      ];

  return (
    <article>
      <PageHeader
        title={zh ? "怎么上线" : "How to publish"}
        lede={
          zh
            ? "dwangust.github.io 这类地址就是 GitHub Pages。文件放在 GitHub 仓库里，由 GitHub 托管，不需要自己买服务器。"
            : "An address like dwangust.github.io is GitHub Pages. The files live in a GitHub repository, and GitHub hosts them. You do not need your own server."
        }
      />

      <section className="mt-8 max-w-2xl space-y-3 leading-7">
        <p>
          {zh
            ? "那个网站能对上三件事：域名是「用户名.github.io」；页面响应头里的服务器是 GitHub.com；页脚写着 Powered by Jekyll & AcademicPages，而 AcademicPages 是 Minimal Mistakes 主题的一个分支。"
            : "Three things line up for that site: the domain is username.github.io, the response header names GitHub.com as the server, and the footer says Powered by Jekyll & AcademicPages. AcademicPages is a fork of the Minimal Mistakes theme."}
        </p>
        <p>
          {zh
            ? "所以它基于 GitHub，但不是把一个 Word 文档传上去。你有一个公开仓库，GitHub 把仓库里的页面编成网站。仓库名如果正好是「用户名.github.io」，网站就在根地址；如果叫别的名字，地址会多一段，变成 用户名.github.io/仓库名。"
            : "So yes, it is based on GitHub, but it is not a document upload. You keep a public repository, and GitHub turns the pages in that repository into a site. If the repository is named username.github.io, the site lives at the root address. Any other name is served at username.github.io/repository-name."}
        </p>
      </section>

      <div className="mt-8 overflow-x-auto">
        <table className="w-full min-w-[36rem] text-left text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="py-2 pr-4 font-medium" />
              <th className="py-2 pr-4 font-medium">
                {zh ? "参考网站" : "The reference site"}
              </th>
              <th className="py-2 font-medium">
                {zh ? "现在这个页面" : "This page"}
              </th>
            </tr>
          </thead>
          <tbody>
            {comparison.map((row) => (
              <tr key={cell(row.label, "en")} className="border-b border-border">
                <th className="py-3 pr-4 font-medium">{cell(row.label, lang)}</th>
                <td className="py-3 pr-4 text-muted-foreground">
                  {cell(row.reference, lang)}
                </td>
                <td className="py-3 text-muted-foreground">{cell(row.here, lang)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <section className="mt-12">
        <h2 className="font-serif text-2xl font-medium tracking-tight">
          {zh ? "和参考站用同一套模板" : "Use the same template as the reference"}
        </h2>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
          {zh
            ? "想要最接近那一站的栏位和版式，直接用 AcademicPages。你主要改 Markdown，不用写程序。"
            : "For the closest match to that site’s sections and layout, start from AcademicPages. You mostly edit Markdown and do not write application code."}
        </p>
        <ol className="mt-5 max-w-2xl space-y-4">
          {academicSteps.map((step, index) => (
            <Step
              key={step.title}
              index={index + 1}
              title={step.title}
              body={step.body}
            />
          ))}
        </ol>
        <p className="mt-4 text-sm">
          <a
            className="text-foreground underline underline-offset-4"
            href="https://github.com/academicpages/academicpages.github.io"
            target="_blank"
            rel="noreferrer"
          >
            academicpages/academicpages.github.io
          </a>
        </p>
      </section>

      <section className="mt-12">
        <h2 className="font-serif text-2xl font-medium tracking-tight">
          {zh ? "继续用现在这个页面" : "Keep using this page"}
        </h2>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
          {zh
            ? "栏目是同一类：关于、论文、报告，侧栏放联系方式。页面先在本地编好，再由 GitHub Actions 发到 Pages。公开仓库可以免费托管。"
            : "The sections are the same kind of homepage: about, papers, and talks, with contact details in the side column. The pages are built locally, then GitHub Actions publishes them. A public repository is free to host."}
        </p>
        <ol className="mt-5 max-w-2xl space-y-4">
          {thisSiteSteps.map((step, index) => (
            <Step
              key={step.title}
              index={index + 1}
              title={step.title}
              body={step.body}
            />
          ))}
        </ol>
        <p className="mt-4 max-w-2xl text-sm leading-6 text-muted-foreground">
          {zh
            ? "如果仓库不叫「用户名.github.io」，发布前要设置环境变量 NEXT_PUBLIC_BASE_PATH=/仓库名，否则样式和链接会对不齐。"
            : "If the repository is not named username.github.io, set NEXT_PUBLIC_BASE_PATH=/repository-name before the build. Otherwise the styles and links will miss their folder."}
        </p>
      </section>

      <p className="mt-10 text-sm text-muted-foreground">
        <a
          className="text-foreground underline underline-offset-4"
          href="https://docs.github.com/zh/pages/getting-started-with-github-pages/about-github-pages"
          target="_blank"
          rel="noreferrer"
        >
          {zh ? "GitHub Pages 官方说明" : "GitHub Pages documentation"}
        </a>
      </p>
    </article>
  );
}
