"use client";

import Link from "next/link";
import { useSite } from "@/components/site-provider";
import { PageHeader } from "@/components/page-header";

export function NotFoundView() {
  const { lang } = useSite();

  return (
    <article>
      <PageHeader
        title={lang === "zh" ? "没有这一页" : "Page not found"}
        lede={
          lang === "zh"
            ? "地址可能写错了。这些栏目都在顶栏。"
            : "That address does not match a page. The sections are in the top bar."
        }
      />
      <p className="mt-6">
        <Link href="/" className="text-primary underline underline-offset-4 hover:text-link-hover">
          {lang === "zh" ? "回到关于" : "Back to about"}
        </Link>
      </p>
    </article>
  );
}
