import type { Metadata } from "next";
import { AirRadarView } from "@/components/air-radar-view";

export const metadata: Metadata = {
  title: "飞机雷达",
  description: "实时查看附近空域的飞机。",
};

export default function AirRadarPage() {
  return <AirRadarView />;
}
