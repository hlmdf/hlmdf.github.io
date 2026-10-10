"use client";

import { profile } from "@/content/profile";
import { pick } from "@/lib/copy";
import { useSite } from "@/components/site-provider";
import { PageHeader } from "@/components/page-header";

export function TalksView() {
  const { lang } = useSite();
  const items = profile.talks;

  return (
    <article>
      <PageHeader title={lang === "zh" ? "报告" : "Talks"} />

      {items.length > 0 ? (
        <ol className="mt-8 divide-y divide-border border-y border-border">
          {items.map((item) => (
            <li
              key={`${item.date}-${item.title.en}`}
              className="grid gap-1 py-5 sm:grid-cols-[7.5rem_1fr] sm:gap-6"
            >
              <p className="text-sm tabular-nums text-muted-foreground">
                {item.date}
              </p>
              <div>
                <div className="flex items-start justify-between gap-3">
                  <h2 className="font-serif text-xl font-medium tracking-tight">
                    {pick(item.title, lang)}
                  </h2>
                  {item.example ? (
                    <span className="shrink-0 rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground">
                      {lang === "zh" ? "示例" : "Sample"}
                    </span>
                  ) : null}
                </div>
                <p className="mt-1 text-sm text-muted-foreground">
                  {pick(item.event, lang)}
                  <span aria-hidden="true"> · </span>
                  {pick(item.place, lang)}
                </p>
              </div>
            </li>
          ))}
        </ol>
      ) : null}
    </article>
  );
}
