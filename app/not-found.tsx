import type { Metadata } from "next";
import { NotFoundView } from "@/components/not-found-view";

export const metadata: Metadata = {
  title: "没有这一页",
};

export default function NotFound() {
  return <NotFoundView />;
}
