import type { Metadata } from "next";
import { AboutView } from "@/components/about-view";

// The root layout owns the "%s · 李璇" template, but Next only applies it to
// child route segments — app/page.tsx shares the "/" segment with the layout,
// so it has to spell the site name out itself.
export const metadata: Metadata = {
  title: { absolute: "李璇 · 武汉大学人工智能学院博士生" },
  description:
    "李璇，武汉大学人工智能学院智能科学与技术专业博士研究生。研究方向包括科技文献多模态理解、图学习与复杂网络。",
};

export default function Page() {
  return <AboutView />;
}
