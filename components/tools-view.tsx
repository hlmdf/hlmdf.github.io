"use client";

import { profile } from "@/content/profile";
import { pick } from "@/lib/copy";
import { useSite } from "@/components/site-provider";
import { Section } from "@/components/page-header";
import { PageFrame } from "@/components/page-toc";

export function ToolsView() {
  const { lang } = useSite();

  const toc = profile.tools.map((group) => ({
    id: group.title.en.toLowerCase().replace(/[^a-z]+/g, "-").replace(/^-|-$/g, ""),
    label: pick(group.title, lang),
  }));

  return (
    <article>
      <PageFrame title={lang === "zh" ? "实用工具" : "Tools"} toc={toc}>
      {profile.tools.map((group, index) => (
        <Section id={toc[index].id} key={group.title.en} title={pick(group.title, lang)}>
          {group.items.length > 0 ? (
            <ul className="max-w-2xl space-y-2">
              {group.items.map((item) => (
                <li key={item.href} className="leading-7">
                  <a
                    className="text-primary underline underline-offset-4 hover:text-link-hover"
                    href={item.href}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {pick(item.name, lang)}
                  </a>
                </li>
              ))}
            </ul>
          ) : null}
        </Section>
      ))}
      </PageFrame>
    </article>
  );
}
