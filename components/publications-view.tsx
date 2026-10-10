"use client";

import { profile, type Publication, type Thesis } from "@/content/profile";
import { pick } from "@/lib/copy";
import { useSite } from "@/components/site-provider";
import { Section } from "@/components/page-header";
import { PageFrame } from "@/components/page-toc";

const sample = `{
  example: false,
  kind: "journal",
  title: { zh: "标题", en: "Title" },
  authors: "Xuan",
  venue: { zh: "期刊或会议", en: "Venue" },
  year: "2026",
  links: [{ label: { zh: "PDF", en: "PDF" }, href: "/files/paper.pdf" }],
}`;

const groups = [
  { kind: "preprint", zh: "预印本", en: "Preprints" },
  { kind: "journal", zh: "期刊", en: "Journals" },
  { kind: "conference", zh: "会议", en: "Conferences" },
] as const;

function Citation({ item }: { item: Publication }) {
  const { lang } = useSite();

  return (
    <li className="py-5">
      <div className="flex items-baseline justify-between gap-4">
        <p className="text-sm tabular-nums text-muted-foreground">{item.year}</p>
        {item.example ? (
          <span className="rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground">
            {lang === "zh" ? "示例" : "Sample"}
          </span>
        ) : null}
      </div>
      <h3 className="mt-1 font-serif text-xl font-medium tracking-tight">
        {pick(item.title, lang)}
      </h3>
      <p className="mt-1 text-sm">{item.authors}</p>
      <p className="text-sm italic text-muted-foreground">{pick(item.venue, lang)}</p>
      {item.links.length > 0 ? (
        <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm">
          {item.links.map((link) => (
            <li key={link.href}>
              <a
                className="text-primary underline underline-offset-4 hover:text-link-hover"
                href={link.href}
                target="_blank"
                rel="noopener noreferrer"
              >
                {pick(link.label, lang)}
              </a>
            </li>
          ))}
        </ul>
      ) : null}
    </li>
  );
}

function ThesisItem({ item }: { item: Thesis }) {
  const { lang } = useSite();

  return (
    <li className="py-5">
      <p className="text-sm tabular-nums text-muted-foreground">{pick(item.year, lang)}</p>
      <h3 className="mt-1 font-serif text-xl font-medium tracking-tight">
        {pick(item.title, lang)}
      </h3>
      <p className="mt-1 text-sm text-muted-foreground">{pick(item.detail, lang)}</p>
      {item.links.length > 0 ? (
        <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm">
          {item.links.map((link) => (
            <li key={link.href}>
              <a
                className="text-primary underline underline-offset-4 hover:text-link-hover"
                href={link.href}
                target="_blank"
                rel="noopener noreferrer"
              >
                {pick(link.label, lang)}
              </a>
            </li>
          ))}
        </ul>
      ) : null}
    </li>
  );
}

export function PublicationsView() {
  const { lang } = useSite();
  const items = profile.publications;
  const showSampleHelp = items.some((item) => item.example);

  const toc = [
    ...groups.map((group) => ({ id: group.kind, label: group[lang] })),
    { id: "theses", label: lang === "zh" ? "毕业论文" : "Theses" },
  ];

  return (
    <article>
      <PageFrame title={lang === "zh" ? "论文" : "Papers"} toc={toc}>
      {groups.map((group) => {
        const groupItems = items.filter((item) => item.kind === group.kind);
        return (
          <Section id={group.kind} key={group.kind} title={group[lang]}>
            {groupItems.length > 0 ? (
              <ol className="-mt-4 divide-y divide-border border-b border-border">
                {groupItems.map((item) => (
                  <Citation key={`${item.year}-${item.title.en}`} item={item} />
                ))}
              </ol>
            ) : null}
          </Section>
        );
      })}

      <Section id="theses" title={lang === "zh" ? "毕业论文" : "Theses"}>
        {profile.theses.length > 0 ? (
          <ol className="-mt-4 divide-y divide-border border-b border-border">
            {profile.theses.map((item) => (
              <ThesisItem key={`${item.year.en}-${item.title.en}`} item={item} />
            ))}
          </ol>
        ) : null}
      </Section>

      {showSampleHelp ? (
        <section className="mt-10">
          <h2 className="font-serif text-2xl font-medium tracking-tight">
            {lang === "zh" ? "怎么加一条" : "How to add one"}
          </h2>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
            {lang === "zh"
              ? "示例条目只用来看版式。写成你自己的工作时，把 example 改成 false。kind 用 preprint、journal 或 conference。PDF 可以放进 public/files/，链接写成 /files/paper.pdf。"
              : "Sample rows only show the layout. When the work is yours, set example to false. Set kind to preprint, journal, or conference. Put a PDF in public/files/ and link it as /files/paper.pdf."}
          </p>
          <pre className="mt-4 overflow-x-auto rounded-lg bg-muted p-4 font-mono text-[0.8125rem] leading-6">
            <code>{sample}</code>
          </pre>
        </section>
      ) : null}
      </PageFrame>
    </article>
  );
}
