"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useSite } from "@/components/site-provider";
import { PageHeader } from "@/components/page-header";
import { cn } from "@/lib/utils";

export type TocItem = { id: string; label: string };

export function PageFrame({
  title,
  lede,
  toc,
  children,
}: {
  title: string;
  lede?: string;
  toc: TocItem[];
  children: ReactNode;
}) {
  return (
    <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_11rem] lg:items-start lg:gap-x-10">
      <PageHeader title={title} lede={lede} />
      <PageToc items={toc} />
      <div className="min-w-0">{children}</div>
    </div>
  );
}

function scrollToSection(id: string, frame: { current: number }) {
  cancelAnimationFrame(frame.current);
  const target = document.getElementById(id);
  if (!target) return;
  const margin = Number.parseFloat(getComputedStyle(target).scrollMarginTop) || 0;
  const top = Math.max(0, target.getBoundingClientRect().top + window.scrollY - margin);
  const start = window.scrollY;
  const distance = top - start;
  history.pushState(null, "", `#${id}`);
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const jump = (y: number) => window.scrollTo({ top: y, behavior: "instant" });
  if (reduce || Math.abs(distance) < 2) {
    jump(top);
    return;
  }
  const duration = Math.min(900, Math.max(520, Math.abs(distance) * 0.6));
  const started = performance.now();
  const step = (now: number) => {
    const t = Math.min(1, (now - started) / duration);
    const eased = t < 0.5 ? 2 * t * t : 1 - ((-2 * t + 2) ** 2) / 2;
    jump(start + distance * eased);
    if (t < 1) frame.current = requestAnimationFrame(step);
  };
  frame.current = requestAnimationFrame(step);
}

function PageToc({ items }: { items: TocItem[] }) {
  const { lang } = useSite();
  const [active, setActive] = useState(items[0]?.id ?? "");
  const scrollFrame = useRef(0);

  const ids = items.map((item) => item.id).join("\n");

  useEffect(() => {
    const nodes = ids
      .split("\n")
      .filter(Boolean)
      .map((id) => document.getElementById(id))
      .filter((node): node is HTMLElement => node !== null);
    if (nodes.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        const id = visible[0]?.target.id;
        if (id) setActive(id);
      },
      { rootMargin: "-20% 0px -55% 0px", threshold: [0, 0.25, 1] },
    );
    for (const node of nodes) observer.observe(node);
    return () => observer.disconnect();
  }, [ids]);

  return (
    <nav
      aria-label={lang === "zh" ? "目录" : "Contents"}
      className="mt-6 lg:sticky lg:top-24 lg:mt-1"
    >
      <p className="text-sm font-medium">{lang === "zh" ? "目录" : "Contents"}</p>
      <ul className="mt-3 space-y-1 border-l border-border">
        {items.map((item) => {
          const current = item.id === active;
          return (
            <li key={item.id}>
              <a
                href={`#${item.id}`}
                aria-current={current ? "true" : undefined}
                onClick={(event) => {
                  event.preventDefault();
                  setActive(item.id);
                  scrollToSection(item.id, scrollFrame);
                }}
                className={cn(
                  "-ml-px block border-l-2 py-1 pl-3 text-sm leading-6",
                  current
                    ? "border-primary font-medium text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground",
                )}
              >
                {item.label}
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
