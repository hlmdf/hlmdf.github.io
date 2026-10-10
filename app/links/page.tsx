import type { Metadata } from "next";
import { LinksView } from "@/components/links-view";

export const metadata: Metadata = {
  title: "网址",
  description: "常用网址。",
};

export default function LinksPage() {
  return <LinksView />;
}
