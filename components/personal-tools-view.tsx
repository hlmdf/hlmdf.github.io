"use client";

import { profile } from "@/content/profile";
import { pick } from "@/lib/copy";
import { useSite } from "@/components/site-provider";
import { PageHeader } from "@/components/page-header";

export function PersonalToolsView() {
  const { lang } = useSite();

  return (
    <article>
      <PageHeader title={lang === "zh" ? "个人工具" : "Personal tools"} />
      <ul className="mt-8 max-w-2xl divide-y divide-border border-y border-border">
        {profile.personalTools.map((item) => (
          <li key={item.name.en} className="py-4 leading-7">
            {item.href ? (
              <a
                className="text-primary underline underline-offset-4 hover:text-link-hover"
                href={item.href}
              >
                {pick(item.name, lang)}
              </a>
            ) : (
              <span>{pick(item.name, lang)}</span>
            )}
          </li>
        ))}
      </ul>
    </article>
  );
}
