import type { Copy, Lang } from "@/content/profile";

export function pick(copy: Copy, lang: Lang) {
  return copy[lang];
}
