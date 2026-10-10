import type { Metadata } from "next";
import { PublishView } from "@/components/publish-view";

export const metadata: Metadata = {
  title: "上线",
  description: "用 GitHub Pages 发布个人主页，包括 AcademicPages 和这个站点两条路。",
};

export default function PublishPage() {
  return <PublishView />;
}
