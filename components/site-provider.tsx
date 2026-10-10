"use client";

import {
  createContext,
  useContext,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import type { Lang } from "@/content/profile";

type SiteContextValue = {
  lang: Lang;
  setLang: (lang: Lang) => void;
};

const SiteContext = createContext<SiteContextValue | null>(null);
const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function readLang(): Lang {
  const stored = localStorage.getItem("lang");
  return stored === "zh" ? "zh" : "en";
}

function emit() {
  listeners.forEach((listener) => listener());
}

export function SiteProvider({ children }: { children: ReactNode }) {
  const lang = useSyncExternalStore(subscribe, readLang, () => "en" as const);

  function setLang(next: Lang) {
    localStorage.setItem("lang", next);
    document.documentElement.lang = next === "zh" ? "zh-CN" : "en";
    emit();
  }

  return (
    <SiteContext.Provider value={{ lang, setLang }}>
      {children}
    </SiteContext.Provider>
  );
}

export function useSite() {
  const value = useContext(SiteContext);
  if (!value) {
    throw new Error("useSite must be used within SiteProvider");
  }
  return value;
}

export function toggleTheme() {
  const root = document.documentElement;
  const nextDark = !root.classList.contains("dark");
  const apply = () => {
    root.classList.toggle("dark", nextDark);
    localStorage.setItem("theme", nextDark ? "dark" : "light");
  };
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduced || typeof document.startViewTransition !== "function") {
    apply();
    return;
  }
  root.classList.add("theme-switching");
  const transition = document.startViewTransition(apply);
  transition.finished.finally(() => root.classList.remove("theme-switching"));
}
