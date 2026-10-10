import type { Metadata } from "next";
import { PublicationsView } from "@/components/publications-view";

export const metadata: Metadata = {
  title: "论文",
  description: "预印本、期刊论文、会议论文和毕业论文。",
};

export default function PublicationsPage() {
  return <PublicationsView />;
}
