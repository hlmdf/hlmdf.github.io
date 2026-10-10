import type { Metadata } from "next";
import { NotesView } from "@/components/notes-view";

export const metadata: Metadata = {
  title: "生活",
  description: "生活记录。",
};

export default function LifePage() {
  return <NotesView section="life" />;
}
