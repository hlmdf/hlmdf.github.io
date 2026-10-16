"use client";

import { useEffect, useRef, useState } from "react";
import { MapPin, X } from "lucide-react";
import { useSite } from "@/components/site-provider";
import { cn } from "@/lib/utils";

/* 【2026-10-16 新增】页脚访客地图
 *
 * 数据流：页面加载 → 本组件向 visitor-map 服务上报一次位置 → 拉回总次数和坐标点
 * 位置由浏览器侧通过 api.ip.sb 查得（城市级），服务器只负责记录和计数。
 * 后端地址可用环境变量 NEXT_PUBLIC_VISITOR_API 覆盖。
 */

const API_BASE = (
  process.env.NEXT_PUBLIC_VISITOR_API || "https://47.103.222.155:5010"
).replace(/\/+$/, "");

const COUNTED_KEY = "visitor-map-counted";
const LEAFLET_VERSION = "1.9.4";
const LEAFLET_CSS = `https://cdn.jsdelivr.net/npm/leaflet@${LEAFLET_VERSION}/dist/leaflet.css`;
const LEAFLET_JS = `https://cdn.jsdelivr.net/npm/leaflet@${LEAFLET_VERSION}/dist/leaflet.js`;
/* 高德瓦片，中国大陆访问快；若想换成 OSM，把下面这行换成
   https://tile.openstreetmap.org/{z}/{x}/{y}.png 即可 */
const TILE_URL =
  "https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=7&x={x}&y={y}&z={z}";
const DOT_COLOR = "#52adc8";

type VisitPoint = {
  lat: number;
  lng: number;
  city?: string;
  country?: string;
  ts: number;
};

type Stats = {
  total: number;
  unique: number;
  updated: number;
  points: VisitPoint[];
};

type LeafletLayer = { addTo(map: LeafletMap): LeafletLayer };
type LeafletMap = {
  remove(): void;
  setView(center: [number, number], zoom: number): void;
  fitBounds(bounds: unknown, options?: Record<string, unknown>): void;
  invalidateSize(): void;
};
type LeafletNamespace = {
  map(el: HTMLElement, options: Record<string, unknown>): LeafletMap;
  tileLayer(url: string, options: Record<string, unknown>): LeafletLayer;
  circleMarker(latlng: [number, number], options: Record<string, unknown>): LeafletLayer;
  latLngBounds(coords: [number, number][]): unknown;
};

let leafletPromise: Promise<LeafletNamespace> | null = null;

function loadLeaflet(): Promise<LeafletNamespace> {
  if (leafletPromise) return leafletPromise;
  leafletPromise = new Promise<LeafletNamespace>((resolve, reject) => {
    const existing = (window as unknown as { L?: LeafletNamespace }).L;
    if (existing) {
      resolve(existing);
      return;
    }
    if (!document.querySelector("link[data-leaflet]")) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = LEAFLET_CSS;
      link.setAttribute("data-leaflet", "1");
      document.head.appendChild(link);
    }
    const script = document.createElement("script");
    script.src = LEAFLET_JS;
    script.async = true;
    script.onload = () => {
      const ns = (window as unknown as { L?: LeafletNamespace }).L;
      if (ns) resolve(ns);
      else reject(new Error("leaflet missing"));
    };
    script.onerror = () => reject(new Error("leaflet failed"));
    document.head.appendChild(script);
  });
  return leafletPromise;
}

/** 按 IP 查一次访客所在城市（拿不到就返回空对象，只计次数不落点） */
async function locate(): Promise<Record<string, unknown>> {
  try {
    const res = await fetch("https://api.ip.sb/geoip", { cache: "no-store" });
    if (!res.ok) return {};
    const data = (await res.json()) as {
      latitude?: number;
      longitude?: number;
      city?: string;
      country?: string;
    };
    if (typeof data.latitude !== "number" || typeof data.longitude !== "number") {
      return {};
    }
    return {
      lat: data.latitude,
      lng: data.longitude,
      city: data.city ?? "",
      country: data.country ?? "",
    };
  } catch {
    return {};
  }
}

async function request(
  path: string,
  body?: Record<string, unknown>,
): Promise<Stats | null> {
  try {
    const res = await fetch(API_BASE + path, {
      method: body ? "POST" : "GET",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store",
    });
    if (!res.ok) return null;
    return (await res.json()) as Stats;
  } catch {
    return null;
  }
}

export function VisitorMap({ className }: { className?: string }) {
  const { lang } = useSite();
  const zh = lang === "zh";
  const [stats, setStats] = useState<Stats | null>(null);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(false);
  const [mapReady, setMapReady] = useState(false);
  const mapBoxRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LeafletMap | null>(null);

  // 上报 + 取数：一次会话只上报一次，避免刷新页面把次数刷爆
  useEffect(() => {
    let alive = true;
    (async () => {
      let counted = true;
      try {
        counted = sessionStorage.getItem(COUNTED_KEY) === "1";
      } catch {
        counted = true; // 隐私模式下读不到 sessionStorage，就当已上报
      }
      let data: Stats | null;
      if (counted) {
        data = await request("/api/stats");
      } else {
        data = await request("/api/visit", await locate());
        if (data) {
          try {
            sessionStorage.setItem(COUNTED_KEY, "1");
          } catch {
            /* 忽略存储失败 */
          }
        }
      }
      if (!alive) return;
      if (data) setStats(data);
      else setFailed(true);
    })();
    return () => {
      alive = false;
    };
  }, []);

  // 打开时按需加载 Leaflet 并绘制
  useEffect(() => {
    if (!open || !stats) return;
    const box = mapBoxRef.current;
    if (!box) return;
    if (mapRef.current) return;

    let cancelled = false;
    (async () => {
      try {
        const L = await loadLeaflet();
        if (cancelled || !mapBoxRef.current) return;
        const map = L.map(mapBoxRef.current, {
          center: [28, 108],
          zoom: 2,
          minZoom: 1,
          maxZoom: 18,
          scrollWheelZoom: true,
          worldCopyJump: true,
          attributionControl: true,
        });
        L.tileLayer(TILE_URL, {
          subdomains: "1234",
          maxZoom: 18,
          attribution: "© 高德地图",
        }).addTo(map);

        const coords: [number, number][] = [];
        for (const p of stats.points) {
          if (typeof p.lat !== "number" || typeof p.lng !== "number") continue;
          coords.push([p.lat, p.lng]);
          L.circleMarker([p.lat, p.lng], {
            radius: 4,
            color: DOT_COLOR,
            weight: 1,
            opacity: 0.9,
            fillColor: DOT_COLOR,
            fillOpacity: 0.5,
          }).addTo(map);
        }
        if (coords.length > 1) {
          map.fitBounds(L.latLngBounds(coords), {
            padding: [28, 28],
            maxZoom: 6,
          });
        } else if (coords.length === 1) {
          map.setView(coords[0], 5);
        }

        mapRef.current = map;
        if (!cancelled) setMapReady(true);
        window.setTimeout(() => mapRef.current?.invalidateSize(), 150);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [open, stats]);

  // 关闭时销毁地图，避免再次打开时尺寸错乱
  useEffect(() => {
    if (open) return;
    if (!mapRef.current) return;
    mapRef.current.remove();
    mapRef.current = null;
    setMapReady(false);
  }, [open]);

  // Esc 关闭
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  if (failed) {
    return (
      <span className={cn("text-muted-foreground", className)}>
        {zh ? "访问统计暂不可用" : "Visitor stats unavailable"}
      </span>
    );
  }

  const count = stats
    ? stats.total.toLocaleString(zh ? "zh-CN" : "en-US")
    : "—";

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className={cn(
          "inline-flex items-center gap-1.5 text-muted-foreground transition-colors hover:text-primary",
          className,
        )}
      >
        <MapPin className="size-4 shrink-0" aria-hidden="true" />
        <span>
          {zh ? <>共 {count} 次访问</> : <>{count} visits</>}
        </span>
      </button>

      {open && stats ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={zh ? "访客地图" : "Visitor map"}
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
        >
          <button
            type="button"
            aria-label={zh ? "关闭" : "Close"}
            onClick={() => setOpen(false)}
            className="absolute inset-0 cursor-default bg-black/45"
          />
          <div className="relative z-10 w-full max-w-md overflow-hidden rounded-xl border border-border bg-background shadow-2xl">
            <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-3">
              <div>
                <p className="font-medium text-foreground">
                  {zh ? "访客地图" : "Visitor map"}
                </p>
                <p className="mt-0.5 text-sm text-muted-foreground">
                  {zh
                    ? <>共 {stats.total.toLocaleString("zh-CN")} 次访问 · 独立访客 {stats.unique.toLocaleString("zh-CN")}</>
                    : <>{stats.total.toLocaleString("en-US")} visits · {stats.unique.toLocaleString("en-US")} unique</>}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label={zh ? "关闭" : "Close"}
                className="-mr-1 -mt-1 rounded p-1 text-muted-foreground transition-colors hover:text-foreground"
              >
                <X className="size-4" />
              </button>
            </div>

            <div className="visitor-map relative h-64 w-full bg-muted">
              <div ref={mapBoxRef} className="absolute inset-0" />
              {!mapReady ? (
                <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-sm text-muted-foreground">
                  {zh ? "地图加载中…" : "Loading map…"}
                </div>
              ) : null}
            </div>

            {stats.points.length === 0 ? (
              <p className="px-5 py-3 text-sm text-muted-foreground">
                {zh ? "还没有访客位置记录。" : "No visitor locations recorded yet."}
              </p>
            ) : null}
          </div>
        </div>
      ) : null}
    </>
  );
}
