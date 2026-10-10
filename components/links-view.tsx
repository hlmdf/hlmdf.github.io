"use client";

import { profile } from "@/content/profile";
import { pick } from "@/lib/copy";
import { useSite } from "@/components/site-provider";
import { Section } from "@/components/page-header";
import { PageFrame } from "@/components/page-toc";

export function LinksView() {
  const { lang } = useSite();
  const toc = profile.sites.map((group) => ({
    id: group.id,
    label: pick(group.title, lang),
  }));

  return (
    <article>
      <PageFrame title={lang === "zh" ? "网址" : "Links"} toc={toc}>
        {profile.sites.map((group) => (
          <Section id={group.id} key={group.id} title={pick(group.title, lang)}>
            <ul className="grid grid-cols-3 gap-x-3 gap-y-6 sm:grid-cols-4 xl:grid-cols-5">
              {group.items.map((site) => (
                <li key={site.href}>
                  <a
                    href={site.href}
                    target="_blank"
                    rel="noreferrer"
                    className="group flex flex-col items-center gap-2 text-center"
                  >
                    <span className="flex size-14 items-center justify-center rounded-full border border-border bg-white transition-colors group-hover:border-primary">
                      <img src={site.icon} alt="" className="size-8 object-contain" />
                    </span>
                    <span className="text-sm leading-5 text-foreground group-hover:text-primary">
                      {pick(site.name, lang)}
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          </Section>
        ))}
      </PageFrame>
    </article>
  );
}
