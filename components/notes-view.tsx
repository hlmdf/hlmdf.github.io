"use client";

import { profile, type Post, type PostImage } from "@/content/profile";
import { pick } from "@/lib/copy";
import { useSite } from "@/components/site-provider";
import { PageHeader, Section } from "@/components/page-header";
import { PageFrame } from "@/components/page-toc";
import { cn } from "@/lib/utils";

function photoOf(image: string | PostImage) {
  if (typeof image === "string") return { src: image, full: image };
  return { src: image.src, full: image.full ?? image.src };
}

function PhotoLink({
  src,
  full,
  alt,
  className,
}: {
  src: string;
  full: string;
  alt: string;
  className?: string;
}) {
  return (
    <a
      href={full}
      target="_blank"
      rel="noopener noreferrer"
      className={cn("block", className)}
    >
      <img src={src} alt={alt} className="w-full rounded-lg" />
    </a>
  );
}

function PhotoSet({
  images,
  alt,
}: {
  images: Array<string | PostImage>;
  alt: string;
}) {
  const photos = images.map(photoOf);
  if (photos.length === 1) {
    const photo = photos[0];
    return (
      <PhotoLink
        src={photo.src}
        full={photo.full}
        alt={alt}
        className="mt-4 max-w-2xl"
      />
    );
  }

  const [lead, ...rest] = photos;
  return (
    <div className="mt-4 max-w-3xl">
      <PhotoLink src={lead.src} full={lead.full} alt={`${alt} 1`} />
      {rest.length > 0 ? (
        <div
          className={cn(
            "mt-3 grid gap-3",
            rest.length > 1 && "sm:grid-cols-2",
          )}
        >
          {rest.map((photo, index) => (
            <PhotoLink
              key={photo.full}
              src={photo.src}
              full={photo.full}
              alt={`${alt} ${index + 2}`}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

const sections = {
  news: { zh: "新闻", en: "News", items: profile.news },
  life: { zh: "生活", en: "Life", items: profile.life },
} as const;

export function NotesView({ section }: { section: keyof typeof sections }) {
  const { lang } = useSite();
  const { items } = sections[section];

  const sorted = [...items].sort((a, b) => b.date.en.localeCompare(a.date.en));

  if (section === "life") {
    const toc = sorted.map((item) => ({
      id: `life-${item.date.en}`,
      label: pick(item.date, lang),
    }));
    return (
      <article>
        <PageFrame title={sections.life[lang]} toc={toc}>
          {sorted.map((item: Post) => (
            <Section
              id={`life-${item.date.en}`}
              key={`${item.date.en}-${item.title.en}`}
              title={pick(item.date, lang)}
            >
              <h3 className="font-serif text-xl font-medium tracking-tight">
                {pick(item.title, lang)}
              </h3>
              {item.body ? (
                <p className="mt-2 max-w-2xl leading-8">{pick(item.body, lang)}</p>
              ) : null}
              {item.images && item.images.length > 0 ? (
                <PhotoSet images={item.images} alt={pick(item.title, lang)} />
              ) : null}
            </Section>
          ))}
        </PageFrame>
      </article>
    );
  }

  return (
    <article>
      <PageHeader title={sections[section][lang]} />

      {sorted.length > 0 ? (
        <ol className="mt-8 divide-y divide-border border-y border-border">
          {sorted.map((item: Post) => (
            <li
              key={`${item.date.en}-${item.title.en}`}
              className="grid gap-1 py-5 sm:grid-cols-[7.5rem_1fr] sm:gap-6"
            >
              <p className="text-sm tabular-nums text-muted-foreground">
                {pick(item.date, lang)}
              </p>
              <div>
                <h2 className="font-serif text-xl font-medium tracking-tight">
                  {pick(item.title, lang)}
                </h2>
                {item.body ? (
                  <p className="mt-2 max-w-2xl leading-8">{pick(item.body, lang)}</p>
                ) : null}
                {item.images && item.images.length > 0 ? (
                  <PhotoSet
                    images={item.images}
                    alt={pick(item.title, lang)}
                  />
                ) : null}
              </div>
            </li>
          ))}
        </ol>
      ) : null}
    </article>
  );
}
