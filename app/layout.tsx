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
  var seen = localStorage.getItem("site-entered") === "1";
  var path = location.pathname.replace(/\\/+$/, "") || "/";
  var home = ${JSON.stringify((process.env.NEXT_PUBLIC_BASE_PATH || "").replace(/\/+$/, "") || "/")};
  if (seen || path !== home) document.documentElement.classList.add("site-entered");
} catch (e) {
  document.documentElement.classList.add("site-entered");
}
`;

export const metadata: Metadata = {
  metadataBase: new URL("https://hlmdf.github.io"),
  title: {
    default: "李璇的主页",
    template: "%s · 李璇的主页",
  },
  description:
    "李璇，武汉大学人工智能学院智能科学与技术专业博士研究生。研究方向包括科技文献多模态理解、图学习与复杂网络。",
  // title and description are left out of purpose: Next falls back to the
  // resolved page metadata, so every page shares the site card without every
  // page showing the same headline.
  openGraph: {
    type: "website",
    locale: "zh_CN",
    alternateLocale: ["en_US"],
    siteName: "李璇的主页",
    images: ["/avatar.jpg"],
  },
  twitter: {
    card: "summary",
    images: ["/avatar.jpg"],
  },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${sourceSans.variable} ${newsreader.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        {/* CJK glyphs fall back to the system stack declared in globals.css. */}
        {/* Loading Noto from fonts.googleapis.com was render-blocking and is
            unreachable from mainland China, so the stylesheet is not requested. */}
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
