import type { MetadataRoute } from "next";
import { profile } from "@/content/profile";

const BASE = "https://hlmdf.github.io";

// output: "export" needs each metadata route to opt into static generation.
export const dynamic = "force-static";

export default function sitemap(): MetadataRoute.Sitemap {
  const routes = [
    "/",
    "/publications/",
    "/life/",
    "/tools/",
    "/links/",
    "/personal/",
    ...(profile.talks.length > 0 ? ["/talks/"] : []),
    ...(profile.news.length > 0 ? ["/news/"] : []),
  ];

  return routes.map((route) => ({
    url: `${BASE}${route}`,
    changeFrequency: "monthly",
    priority: route === "/" ? 1 : 0.7,
  }));
}
