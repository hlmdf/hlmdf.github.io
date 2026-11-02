import type { Metadata } from "next";
import { AboutView } from "@/components/about-view";

// The root layout's template does not reach this page: Next only applies
// title.template to child route segments, and app/page.tsx shares the "/"
// segment with the layout. Spelling it out keeps "关于 · 李璇的主页" consistent
// with how every other page is titled.
export const metadata: Metadata = {
  title: { absolute: "关于 · 李璇的主页" },
  description:
    "李璇，武汉大学人工智能学院智能科学与技术专业博士研究生。研究方向包括科技文献多模态理解、图学习与复杂网络。",
};

export default function Page() {
  return <AboutView />;
}
