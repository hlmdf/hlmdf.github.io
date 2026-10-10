import type { Metadata } from "next";
import { Geist_Mono, Newsreader, Source_Sans_3 } from "next/font/google";
import Script from "next/script";
import { SiteProvider } from "@/components/site-provider";
import { SiteShell } from "@/components/site-shell";
import "./globals.css";

const sourceSans = Source_Sans_3({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-source-sans",
  display: "swap",
});

const newsreader = Newsreader({
  subsets: ["latin"],
  style: ["normal", "italic"],
  variable: "--font-newsreader",
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const themeScript = `
try {
  var storedTheme = localStorage.getItem("theme");
  var prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  var dark = storedTheme ? storedTheme === "dark" : prefersDark;
  document.documentElement.classList.toggle("dark", dark);
  var storedLang = localStorage.getItem("lang");
  document.documentElement.lang = storedLang === "zh" ? "zh-CN" : "en";
} catch (e) {}
`;

const enteredBoot = `
try {
  var entered = sessionStorage.getItem("site-entered") === "1";
  var path = location.pathname.replace(/\\/+$/, "") || "/";
  var home = ${JSON.stringify((process.env.NEXT_PUBLIC_BASE_PATH || "").replace(/\/+$/, "") || "/")};
  if (entered || path !== home) document.documentElement.classList.add("site-entered");
} catch (e) {}
`;

export const metadata: Metadata = {
  title: {
    default: "李璇",
    template: "%s · 李璇",
  },
  description: "李璇的个人主页。简介、论文和报告。",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${sourceSans.variable} ${newsreader.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        {/* CJK is not a next/font subset for Noto Sans SC, so the stylesheet is loaded here. */}
        {/* eslint-disable-next-line @next/next/no-page-custom-font */}
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;600&family=Noto+Serif+SC:wght@500;600&display=swap"
        />
        <script dangerouslySetInnerHTML={{ __html: enteredBoot }} />
        <style
          dangerouslySetInnerHTML={{
            __html: `
::view-transition-old(root),::view-transition-new(root){animation:none!important}
html.theme-switching,html.theme-switching *{transition:none!important}
html.theme-switching::view-transition-old(root){animation:480ms ease both theme-fade-out!important}
html.theme-switching::view-transition-new(root){animation:480ms ease both theme-fade-in!important}
@keyframes theme-fade-out{to{opacity:0}}
@keyframes theme-fade-in{from{opacity:0}}
@media (prefers-reduced-motion:reduce){
  html.theme-switching::view-transition-old(root),
  html.theme-switching::view-transition-new(root){animation-duration:0s!important}
}
`,
          }}
        />
      </head>
      <body className="min-h-full bg-background text-foreground">
        <Script id="theme-lang" strategy="beforeInteractive">
          {themeScript}
        </Script>
        <SiteProvider>
          <SiteShell>{children}</SiteShell>
        </SiteProvider>
      </body>
    </html>
  );
}
