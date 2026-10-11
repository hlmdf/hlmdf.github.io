"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { GraduationCap, Mail, MapPin, Menu, Moon, Sun, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { HeaderStatus } from "@/components/header-status";
import { toggleTheme, useSite } from "@/components/site-provider";
import {
  isPlaceholderEmail,
  isPlaceholderGithub,
  profile,
} from "@/content/profile";
import { pick } from "@/lib/copy";
import { cn } from "@/lib/utils";

const nav = [
  { href: "/", zh: "关于", en: "About" },
  { href: "/publications", zh: "论文", en: "Papers" },
  { href: "/talks", zh: "报告", en: "Talks" },
  { href: "/news", zh: "新闻", en: "News" },
  { href: "/life", zh: "生活", en: "Life" },
  { href: "/tools", zh: "实用工具", en: "Tools" },
  { href: "/links", zh: "网址", en: "Links" },
  { href: "/personal", zh: "个人工具", en: "Personal" },
] as const;

function WechatIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M9.2 3.6c-3.7 0-6.7 2.5-6.7 5.6 0 1.8 1 3.3 2.7 4.4l-.7 2.2 2.4-1.2c.7.2 1.4.3 2.2.3.2 0 .4 0 .6 0-.2-.5-.3-1-.3-1.5 0-3.3 3.2-6 7.2-6 .3 0 .5 0 .8 0C16.4 5.4 13.1 3.6 9.2 3.6zm-2.2 4.4a1 1 0 1 1 0-2 1 1 0 0 1 0 2zm4.3 0a1 1 0 1 1 0-2 1 1 0 0 1 0 2z" />
      <path d="M21.4 13.4c0-2.7-2.6-4.9-5.8-4.9s-5.8 2.2-5.8 4.9 2.6 4.9 5.8 4.9c.6 0 1.2-.1 1.8-.2l2.2 1.2-.6-1.9c1.5-.9 2.4-2.2 2.4-4zm-7.6-.8a.8.8 0 1 1 0-1.6.8.8 0 0 1 0 1.6zm3.6 0a.8.8 0 1 1 0-1.6.8.8 0 0 1 0 1.6z" />
    </svg>
  );
}

function GithubIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0 1 12 6.844a9.56 9.56 0 0 1 2.504.337c1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0 0 22 12.017C22 6.484 17.522 2 12 2z" />
    </svg>
  );
}

function normalize(path: string) {
  if (path.length > 1 && path.endsWith("/")) return path.slice(0, -1);
  return path || "/";
}

type Phase = "cover" | "moving" | "returning" | "in";

const MOVE_MS = 700;
const ENTERED_KEY = "site-entered";

function prefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function SiteShell({ children }: { children: ReactNode }) {
  const pathname = normalize(usePathname() || "/");
  const router = useRouter();
  const { lang, setLang } = useSite();
  const [menuPath, setMenuPath] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>(pathname === "/" ? "cover" : "in");
  const identityRef = useRef<HTMLDivElement>(null);
  const fromRect = useRef<DOMRect | null>(null);
  const fromAvatar = useRef<DOMRect | null>(null);
  const holdHeight = useRef(0);
  const pendingHome = useRef(false);
  const flipToken = useRef(0);
  const open = menuPath === pathname;
  const year = new Date().getFullYear();
  const emailMissing = isPlaceholderEmail(profile.email);
  const githubMissing = isPlaceholderGithub(profile.github);
  const coverLayout = phase === "cover" || phase === "returning";
  const revealed = phase === "in";
  const headerSolid = revealed || phase === "returning";
  const veil = cn(
    "transition-opacity duration-700",
    revealed ? "opacity-100" : "pointer-events-none opacity-0",
  );

  function rememberPosition() {
    const el = identityRef.current;
    if (!el) return false;
    fromRect.current = el.getBoundingClientRect();
    fromAvatar.current = el.querySelector("img")?.getBoundingClientRect() ?? null;
    return true;
  }

  function enter() {
    if (phase !== "cover") return;
    try {
      sessionStorage.setItem(ENTERED_KEY, "1");
    } catch {
      // Storage can be blocked. The cover still closes for this view.
    }
    if (!rememberPosition() || prefersReducedMotion()) {
      setPhase("in");
      return;
    }
    setPhase("moving");
  }

  function finishReturn() {
    if (pendingHome.current) {
      pendingHome.current = false;
      router.push("/");
    }
    setPhase("cover");
  }

  function returnToCover() {
    if (phase !== "in") return;
    try {
      sessionStorage.removeItem(ENTERED_KEY);
    } catch {
      // Storage can be blocked. This view still returns to the cover.
    }
    document.documentElement.classList.remove("site-entered");
    pendingHome.current = pathname !== "/";
    if (!rememberPosition() || prefersReducedMotion()) {
      finishReturn();
      return;
    }
    holdHeight.current = fromRect.current?.height ?? 0;
    setPhase("returning");
  }

  useLayoutEffect(() => {
    if (phase === "returning") return;
    let entered = false;
    try {
      entered = sessionStorage.getItem(ENTERED_KEY) === "1";
    } catch {
      entered = false;
    }
    if (pathname !== "/" && phase === "in") {
      try {
        sessionStorage.setItem(ENTERED_KEY, "1");
      } catch {
        // Ignore storage failures and keep the current page.
      }
      return;
    }
    if (entered && phase === "cover") setPhase("in");
  }, [pathname, phase]);

  useLayoutEffect(() => {
    const from = fromRect.current;
    const el = identityRef.current;
    const settling = phase === "moving" || phase === "returning";
    if (!from || !el || !settling) return;
    const node = el;
    const nextPhase: Phase = phase === "returning" ? "cover" : "in";

    const to = el.getBoundingClientRect();
    const dx = from.left - to.left;
    const dy = from.top - to.top;
    const img = el.querySelector("img");
    const avatarTo = img?.getBoundingClientRect();
    const avatarScale =
      img && fromAvatar.current && avatarTo && avatarTo.width > 0
        ? fromAvatar.current.width / avatarTo.width
        : 1;
    const token = ++flipToken.current;

    function clearMotion() {
      node.style.transition = "";
      node.style.transform = "";
      if (!img) return;
      img.style.transition = "";
      img.style.transform = "";
    }

    if (Math.hypot(dx, dy) < 1 && Math.abs(avatarScale - 1) < 0.02) {
      fromRect.current = null;
      clearMotion();
      if (nextPhase === "cover") finishReturn();
      else setPhase(nextPhase);
      return;
    }

    const extraX =
      img && fromAvatar.current && avatarTo
        ? fromAvatar.current.left - (avatarTo.left + dx)
        : 0;
    const extraY =
      img && fromAvatar.current && avatarTo
        ? fromAvatar.current.top - (avatarTo.top + dy)
        : 0;
    const easing = "cubic-bezier(0.22, 1, 0.36, 1)";
    const group = el.animate(
      [
        { transform: `translate(${dx}px, ${dy}px)` },
        { transform: "translate(0px, 0px)" },
      ],
      { duration: MOVE_MS, easing, fill: "both" },
    );
    const avatar = img
      ? img.animate(
          [
            {
              transformOrigin: "top left",
              transform: `translate(${extraX}px, ${extraY}px) scale(${avatarScale})`,
            },
            {
              transformOrigin: "top left",
              transform: "translate(0px, 0px) scale(1)",
            },
          ],
          { duration: MOVE_MS, easing, fill: "both" },
        )
      : null;

    let cancelled = false;
    Promise.all([group.finished, avatar?.finished]).then(() => {
      if (cancelled || token !== flipToken.current) return;
      group.cancel();
      avatar?.cancel();
      fromRect.current = null;
      if (nextPhase === "cover") finishReturn();
      else setPhase(nextPhase);
    });

    return () => {
      cancelled = true;
      group.cancel();
      avatar?.cancel();
    };
  }, [phase]);

  return (
    <div
      data-shell
      className={cn(
        "flex min-h-dvh flex-col",
        (phase === "cover" || phase === "moving") && "h-dvh overflow-hidden",
      )}
    >
      <header
        data-header
        className={cn(
          "sticky top-0 z-30 border-b backdrop-blur-md",
          headerSolid
            ? "border-border bg-background/90"
            : "border-transparent bg-transparent",
        )}
      >
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-5 py-3">
          <button
            type="button"
            data-veil
            onClick={returnToCover}
            className={cn(
              "font-serif text-xl font-medium tracking-tight",
              revealed && "cursor-pointer hover:text-primary",
              veil,
            )}
          >
            {pick(profile.siteTitle, lang)}
          </button>
          <nav
            data-veil
            className={cn(
              "hidden items-center gap-5 md:flex",
              veil,
            )}
            aria-label="Primary"
            aria-hidden={!revealed}
          >
            {nav.map((item) => {
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  transitionTypes={["page-fade"]}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "border-b-2 pb-0.5 text-sm transition-colors",
                    active
                      ? "border-primary font-medium text-foreground"
                      : "border-transparent text-muted-foreground hover:text-foreground",
                  )}
                >
                  {item[lang]}
                </Link>
              );
            })}
          </nav>
          <div className="ml-auto flex items-center gap-1">
            <Button
              type="button"
              size="sm"
              variant={lang === "en" ? "secondary" : "ghost"}
              aria-pressed={lang === "en"}
              onClick={() => setLang("en")}
            >
              EN
            </Button>
            <Button
              type="button"
              size="sm"
              variant={lang === "zh" ? "secondary" : "ghost"}
              aria-pressed={lang === "zh"}
              onClick={() => setLang("zh")}
            >
              中文
            </Button>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              onClick={toggleTheme}
              aria-label={lang === "zh" ? "切换深色模式" : "Toggle color theme"}
            >
              <Sun className="hidden dark:block" />
              <Moon className="block dark:hidden" />
            </Button>
            <HeaderStatus />
            <Button
              type="button"
              size="icon"
              variant="ghost"
              data-veil
              className={cn("md:hidden", veil)}
              aria-expanded={open}
              aria-hidden={!revealed}
              aria-label={lang === "zh" ? "打开菜单" : "Open menu"}
              onClick={() => setMenuPath(open ? null : pathname)}
            >
              {open ? <X /> : <Menu />}
            </Button>
          </div>
        </div>
        {open && revealed ? (
          <nav
            className="border-t border-border px-5 py-3 md:hidden"
            aria-label="Mobile"
          >
            <ul className="grid gap-1">
              {nav.map((item) => {
                const active = pathname === item.href;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      transitionTypes={["page-fade"]}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "block rounded-md px-3 py-2 text-sm",
                        active
                          ? "bg-muted font-medium text-foreground"
                          : "text-muted-foreground",
                      )}
                    >
                      {item[lang]}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>
        ) : null}
      </header>

      <div className="mx-auto grid w-full max-w-6xl flex-1 gap-8 px-5 py-8 lg:grid-cols-[18rem_minmax(0,1fr)] lg:gap-14 lg:py-12">
        <aside className="lg:sticky lg:top-24 lg:self-start">
          {phase === "returning" && holdHeight.current > 0 ? (
            <div aria-hidden style={{ height: holdHeight.current }} />
          ) : null}
          <div
            data-cover
            className={cn(
              coverLayout &&
                "fixed inset-0 z-20 flex items-center justify-center px-6",
            )}
          >
            <div
              data-cover-stack
              className={cn(coverLayout && "flex flex-col items-center")}
            >
              <div
                ref={identityRef}
                data-identity
                className={cn(
                  "w-max",
                  coverLayout
                    ? "flex flex-col items-center text-center"
                    : "flex items-center gap-4 lg:block",
                )}
              >
                <button
                  type="button"
                  onClick={phase === "cover" ? enter : undefined}
                  className={cn(
                    "rounded-full",
                    phase === "cover" ? "cursor-pointer" : "cursor-default",
                  )}
                  aria-label={phase === "cover" ? (lang === "zh" ? "进入" : "Enter") : undefined}
                >
                  <img
                    src={profile.avatar}
                    alt=""
                    data-avatar
                    className={cn(
                      "shrink-0 rounded-full border border-border object-cover object-[center_68%] shadow-[0_0_0_4px_var(--background),0_0_0_5px_var(--border)]",
                      coverLayout ? "size-36 sm:size-44" : "size-16 lg:size-28",
                    )}
                  />
                </button>
                <div data-identity-text className={cn(coverLayout ? "mt-5" : "lg:mt-4")}>
                  <p className="font-serif text-2xl font-medium tracking-tight">
                    {pick(profile.name, lang)}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {pick(profile.role, lang)}
                  </p>
                  <div className="mt-1 text-sm leading-6">
                    {profile.lab.map((line) => (
                      <a
                        key={line.href}
                        className="block text-foreground underline decoration-[#bdc1c4] underline-offset-4 hover:text-primary hover:decoration-primary"
                        href={line.href}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {pick(line.name, lang)}
                      </a>
                    ))}
                  </div>
                </div>
              </div>
              {coverLayout ? (
                <button
                  type="button"
                  data-enter
                  onClick={enter}
                  aria-hidden={phase !== "cover"}
                  tabIndex={phase === "cover" ? 0 : -1}
                  className={cn(
                    "mt-8 text-sm text-muted-foreground underline decoration-[#bdc1c4] underline-offset-4 hover:text-primary hover:decoration-primary",
                    phase !== "cover" && "invisible",
                  )}
                >
                  {lang === "zh" ? "进入" : "Enter"}
                </button>
              ) : null}
            </div>
          </div>
          <ul
            data-veil
            className={cn(
              "mt-4 space-y-2 text-sm text-muted-foreground lg:mt-6",
              veil,
            )}
            aria-hidden={!revealed}
          >
            <li className="flex items-start gap-2">
              <MapPin className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              <a
                className="text-foreground underline decoration-[#bdc1c4] underline-offset-4 hover:text-primary hover:decoration-primary"
                href={profile.map}
                target="_blank"
                rel="noreferrer"
              >
                {pick(profile.place, lang)}
              </a>
            </li>
            <li>
              {emailMissing ? (
                <span className="inline-flex items-center gap-2">
                  <Mail className="size-4 shrink-0" aria-hidden="true" />
                  {lang === "zh" ? "邮箱还没写" : "Email not added yet"}
                </span>
              ) : (
                <span className="inline-flex items-center gap-2">
                  <Mail className="size-4 shrink-0" aria-hidden="true" />
                  <a
                    className="text-foreground underline decoration-[#bdc1c4] underline-offset-4 hover:text-primary hover:decoration-primary"
                    href={`mailto:${profile.email}`}
                  >
                    {profile.email}
                  </a>
                </span>
              )}
            </li>
            <li>
              <span className="inline-flex items-center gap-2">
                <WechatIcon className="size-4 shrink-0" />
                <span className="text-foreground">
                  {lang === "zh" ? "微信号" : "WeChat ID"} {profile.wechat}
                </span>
              </span>
            </li>
            <li>
              {githubMissing ? (
                <span className="inline-flex items-center gap-2">
                  <GithubIcon className="size-4 shrink-0" />
                  {lang === "zh" ? "GitHub 还没写" : "GitHub not added yet"}
                </span>
              ) : (
                <a
                  className="inline-flex items-center gap-2 text-foreground underline decoration-[#bdc1c4] underline-offset-4 hover:text-primary hover:decoration-primary"
                  href={profile.github}
                  target="_blank"
                  rel="noreferrer"
                >
                  <GithubIcon className="size-4 shrink-0" />
                  GitHub
                </a>
              )}
            </li>
            <li>
              {profile.scholar ? (
                <a
                  className="inline-flex items-center gap-2 text-foreground underline decoration-[#bdc1c4] underline-offset-4 hover:text-primary hover:decoration-primary"
                  href={profile.scholar}
                  target="_blank"
                  rel="noreferrer"
                >
                  <GraduationCap className="size-4 shrink-0" aria-hidden="true" />
                  Google Scholar
                </a>
              ) : (
                <span className="inline-flex items-center gap-2">
                  <GraduationCap className="size-4 shrink-0" aria-hidden="true" />
                  Google Scholar
                </span>
              )}
            </li>
            {profile.cv ? (
              <li>
                <a
                  className="text-foreground underline decoration-[#bdc1c4] underline-offset-4 hover:text-primary hover:decoration-primary"
                  href={profile.cv}
                >
                  {lang === "zh" ? "简历" : "CV"}
                </a>
              </li>
            ) : null}
          </ul>
        </aside>
        <main data-veil className={cn("min-w-0", veil)} aria-hidden={!revealed}>
          {children}
        </main>
      </div>

      <footer data-veil className={cn("border-t border-border", veil)} aria-hidden={!revealed}>
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-5 py-6 text-sm text-muted-foreground sm:flex-row sm:items-baseline sm:justify-between">
          <p>
            © {year} {pick(profile.name, lang)}
          </p>
        </div>
      </footer>
    </div>
  );
}
