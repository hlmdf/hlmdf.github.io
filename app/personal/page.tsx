import type { Metadata } from "next";
import { PersonalToolsView } from "@/components/personal-tools-view";

export const metadata: Metadata = {
  title: "个人工具",
  description: "个人工具。",
};

export default function PersonalPage() {
  return <PersonalToolsView />;
}
