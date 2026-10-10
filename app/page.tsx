import type { Metadata } from "next";
import { AboutView } from "@/components/about-view";

export const metadata: Metadata = {
  title: "关于",
  description: "李璇的简介、正在关注的方向和教育经历。",
};

export default function Page() {
  return <AboutView />;
}
