import type { Metadata } from "next";
import { NotesView } from "@/components/notes-view";

export const metadata: Metadata = {
  title: "新闻",
  description: "近况和消息。",
};

export default function NewsPage() {
  return <NotesView section="news" />;
}
