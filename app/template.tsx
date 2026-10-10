"use client";

import { ViewTransition, type ReactNode } from "react";

export default function Template({ children }: { children: ReactNode }) {
  return (
    <ViewTransition
      enter={{ "page-fade": "page-fade", default: "none" }}
      exit={{ "page-fade": "page-fade", default: "none" }}
      default="none"
    >
      {children}
    </ViewTransition>
  );
}
