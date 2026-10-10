import type { Metadata } from "next";
import { TalksView } from "@/components/talks-view";

export const metadata: Metadata = {
  title: "报告",
  description: "组会、课程展示和会议报告。",
};

export default function TalksPage() {
  return <TalksView />;
}
