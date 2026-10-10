import type { Metadata } from "next";
import { ToolsView } from "@/components/tools-view";

export const metadata: Metadata = {
  title: "实用工具",
  description: "常用工具。",
};

export default function ToolsPage() {
  return <ToolsView />;
}
