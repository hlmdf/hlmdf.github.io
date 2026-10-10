"use client";

import { profile } from "@/content/profile";
import { pick } from "@/lib/copy";
import { useSite } from "@/components/site-provider";
import { Section } from "@/components/page-header";
import { PageFrame } from "@/components/page-toc";

function InterestLine({ text }: { text: string }) {
  const colon = text.includes("：") ? "：" : text.includes(":") ? ":" : "";
  if (!colon) return <span>{text}</span>;
  const [title, ...rest] = text.split(colon);
  return (
    <span>
      <span className="font-medium text-foreground">{title}</span>
      {colon}
      {rest.join(colon)}
    </span>
  );
}

export function AboutView() {
  const { lang } = useSite();

  const toc = [
    { id: "bio", label: lang === "zh" ? "简介" : "Short bio" },
    { id: "interests", label: pick(profile.interestsTitle, lang) },
    { id: "education", label: lang === "zh" ? "教育" : "Education" },
  ];

  return (
    <article>
      <PageFrame title={lang === "zh" ? "关于我" : "About me"} toc={toc}>
      {pick(profile.lookingFor, lang) ? (
        <p className="mt-8 max-w-2xl border-l-2 border-primary pl-4 leading-8 text-muted-foreground">
          {pick(profile.lookingFor, lang)}
        </p>
      ) : null}

      <Section id="bio" title={lang === "zh" ? "简介" : "Short bio"}>
        <div className="max-w-2xl space-y-4 leading-8">
          {profile.bio.map((paragraph) => (
            <p key={paragraph.en}>{pick(paragraph, lang)}</p>
          ))}
          <p>
            {lang === "zh" ? "完整简历可以在" : "You can find my full CV "}
            {profile.cv ? (
              <a
                className="text-primary underline underline-offset-4 hover:text-link-hover"
                href={profile.cv}
                target="_blank"
                rel="noreferrer"
              >
                {lang === "zh" ? "这里" : "here"}
              </a>
            ) : (
              <span className="text-primary underline underline-offset-4">
                {lang === "zh" ? "这里" : "here"}
              </span>
            )}
            {lang === "zh" ? "查看。" : "."}
          </p>
        </div>
      </Section>

      <Section id="interests" title={pick(profile.interestsTitle, lang)}>
        <ul className="max-w-2xl space-y-2">
          {profile.interests.map((item) => (
            <li key={item.en} className="flex gap-3 leading-7">
              <span className="mt-3 size-1.5 shrink-0 rounded-full bg-primary" />
              <InterestLine text={pick(item, lang)} />
            </li>
          ))}
        </ul>
      </Section>

      <Section id="education" title={lang === "zh" ? "教育" : "Education"}>
        <ol className="max-w-2xl divide-y divide-border border-y border-border">
          {profile.education.map((item) => (
            <li
              key={`${item.years.en}-${item.school.en}`}
              className="grid gap-1 py-4 sm:grid-cols-[8.5rem_1fr] sm:gap-6"
            >
              <p className="text-sm text-muted-foreground">{pick(item.years, lang)}</p>
              <div className="flex items-start gap-3">
                <img
                  src={item.crest}
                  alt=""
                  width={56}
                  height={56}
                  className="mt-0.5 size-14 shrink-0"
                />
                <div>
                  <a
                    href={item.href}
                    target="_blank"
                    rel="noreferrer"
                    className="font-medium text-primary underline underline-offset-4 hover:text-link-hover"
                  >
                    {pick(item.school, lang)}
                  </a>
                  <p className="text-sm leading-6 text-muted-foreground">
                    {pick(item.detail, lang)}
                  </p>
                </div>
              </div>
            </li>
          ))}
        </ol>
      </Section>
      </PageFrame>
    </article>
  );
}
