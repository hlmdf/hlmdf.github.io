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
  try {
    return localStorage.getItem("lang") === "zh" ? "zh" : "en";
  } catch {
    // Storage can be blocked (private mode, enterprise policy, embedded frame).
    // Falling back keeps the shell mounted instead of throwing out of the store.
    return "en";
  }
}

function emit() {
  listeners.forEach((listener) => listener());
}

export function SiteProvider({ children }: { children: ReactNode }) {
  const lang = useSyncExternalStore(subscribe, readLang, () => "en" as const);

  function setLang(next: Lang) {
    try {
      localStorage.setItem("lang", next);
    } catch {
      // Language still switches for this view when storage is unavailable.
    }
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
    try {
      localStorage.setItem("theme", nextDark ? "dark" : "light");
    } catch {
      // The theme still applies for this view when storage is unavailable.
    }
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
