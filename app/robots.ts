import type { MetadataRoute } from "next";

// output: "export" needs each metadata route to opt into static generation.
export const dynamic = "force-static";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/" }],
    sitemap: "https://hlmdf.github.io/sitemap.xml",
  };
}
