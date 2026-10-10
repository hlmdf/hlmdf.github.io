import type { ReactNode } from "react";

export function PageHeader({
  title,
  lede,
}: {
  title: string;
  lede?: string;
}) {
  return (
    <header>
      <h1 className="font-serif text-3xl font-medium tracking-tight sm:text-4xl">
        {title}
      </h1>
      {lede ? (
        <p className="mt-4 max-w-2xl text-lg leading-8 text-muted-foreground">
          {lede}
        </p>
      ) : null}
    </header>
  );
}

export function Section({
  id,
  title,
  children,
}: {
  id?: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="mt-11 scroll-mt-28">
      <h2 className="border-b border-border pb-2 font-serif text-2xl font-medium tracking-tight">
        {title}
      </h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}
