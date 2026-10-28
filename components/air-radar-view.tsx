"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import { useSite } from "@/components/site-provider";
import { PageHeader } from "@/components/page-header";
import { cn } from "@/lib/utils";

/* 【2026-10-28 新增】飞机实时雷达
 *
 * 数据流：地图加载 → 按当前视野中心 + 缩放级别向本站转发服务（tools/air-radar）
 * 要附近飞机，转发服务再去问免费的 ADS-B 公开接口 adsb.lol。
 * 必须中转的原因：adsb.lol 等接口不允许浏览器跨域直连。
 * 每 6 秒自动刷新，刷新间隙按航向+速度推算位置（平滑移动）；拖动/缩放地图也会重新查询。
 * 地图底图与页脚访客地图一致：Leaflet 走 CDN 按需加载 + 高德瓦片。
 */

const LEAFLET_VERSION = "1.9.4";
const LEAFLET_CSS = `https://cdn.jsdelivr.net/npm/leaflet@${LEAFLET_VERSION}/dist/leaflet.css`;
const LEAFLET_JS = `https://cdn.jsdelivr.net/npm/leaflet@${LEAFLET_VERSION}/dist/leaflet.js`;
const TILE_URL =
  "https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=7&x={x}&y={y}&z={z}";

/* 转发服务地址（tools/air-radar/server.py），可用环境变量覆盖 */
const API_BASE = (
  process.env.NEXT_PUBLIC_RADAR_API || "https://47.103.222.155:5011"
).replace(/\/+$/, "");

/* 默认视野：武汉上空；接口单次最多查 250 海里半径 */
const DEFAULT_CENTER: [number, number] = [30.6, 114.3];
const DEFAULT_ZOOM = 7;
/* 【2026-10-28 修改】6 秒拉一次新数据；刷新间隙按航向+速度做推算，飞机在地图上是平滑滑行的 */
const REFRESH_MS = 6_000;
/* 飞出查询范围的飞机多保留一会儿，避免在覆盖边缘来回闪 */
const STALE_MS = 30_000;

type Aircraft = {
  hex: string;
  flight?: string;
  lat?: number;
  lon?: number;
  alt_baro?: number | "ground";
  gs?: number;
  track?: number;
  t?: string;
  r?: string;
  squawk?: string;
  /* 【2026-10-28 新增】垂直速度，英尺/分钟，正值爬升、负值下降 */
  baro_rate?: number;
};

/* 【2026-10-28 新增】实拍照片（来自 planespotters.net，经本站服务器中转） */
type PhotoInfo = { src: string; link: string; photographer: string } | null;

type LeafletMarker = {
  addTo(map: LeafletMap): LeafletMarker;
  setLatLng(latlng: [number, number]): LeafletMarker;
  setIcon(icon: unknown): LeafletMarker;
  bindPopup(content: string): LeafletMarker;
  getPopup(): { setContent(content: string): void } | null;
  on(event: string, fn: () => void): LeafletMarker;
  remove(): void;
};
type LeafletCircle = {
  addTo(map: LeafletMap): LeafletCircle;
  setLatLng(latlng: [number, number]): LeafletCircle;
  setRadius(meters: number): LeafletCircle;
  remove(): void;
};
type LeafletMap = {
  remove(): void;
  setView(center: [number, number], zoom: number): void;
  getCenter(): { lat: number; lng: number };
  getZoom(): number;
  on(event: string, fn: () => void): void;
  removeLayer(layer: LeafletMarker): void;
  invalidateSize(): void;
};
type LeafletNamespace = {
  map(el: HTMLElement, options: Record<string, unknown>): LeafletMap;
  tileLayer(url: string, options: Record<string, unknown>): { addTo(map: LeafletMap): void };
  marker(latlng: [number, number], options: Record<string, unknown>): LeafletMarker;
  circle(center: [number, number], options: Record<string, unknown>): LeafletCircle;
  divIcon(options: Record<string, unknown>): unknown;
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

/* 【2026-10-28 修改】半径整体调大（上限 250 海里是上游接口的硬限制），
   减少"地图上明明看着不远、却没查到"的情况；圈的大小画在地图上 */
function radiusForZoom(zoom: number): number {
  if (zoom >= 10) return 80;
  if (zoom === 9) return 120;
  if (zoom === 8) return 180;
  return 250;
}

async function fetchAircraft(lat: number, lon: number, radiusNm: number): Promise<Aircraft[]> {
  const url = `${API_BASE}/api/aircraft?lat=${lat.toFixed(4)}&lon=${lon.toFixed(4)}&r=${radiusNm}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`radar api ${res.status}`);
  const data = (await res.json()) as { ac?: Aircraft[] };
  return Array.isArray(data.ac) ? data.ac : [];
}

const esc = (s: string) =>
  s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string);

export function AirRadarView() {
  const { lang } = useSite();
  const zh = lang === "zh";
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const [count, setCount] = useState(0);
  const [radiusNm, setRadiusNm] = useState(0);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [spinning, setSpinning] = useState(false);
  const mapBoxRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const leafletRef = useRef<LeafletNamespace | null>(null);
  /* 【2026-10-28 新增】虚线圈：标出当前查询半径的覆盖范围 */
  const circleRef = useRef<LeafletCircle | null>(null);
  /* 已画在图上的飞机：key 是飞机 hex，刷新时更新快照而不是重画，避免闪烁 */
  /* 【2026-10-28 修改】快照多存位置/航向/速度，供刷新间隙做航迹推算（平滑移动） */
  const markersRef = useRef(
    new Map<
      string,
      {
        marker: LeafletMarker;
        seenAt: number;
        lat: number;
        lon: number;
        track: number;
        gs: number;
        onGround: boolean;
        baseAt: number;
      }
    >(),
  );
  const inFlightRef = useRef(false);
  /* 【2026-10-28 新增】照片缓存：查过的飞机不重复请求；undefined=没查过 */
  const photoCacheRef = useRef(new Map<string, PhotoInfo>());
  const langRef = useRef(zh);
  langRef.current = zh;

  const popupHtml = (ac: Aircraft): string => {
    const isZh = langRef.current;
    const rows: [string, string][] = [
      [isZh ? "机型" : "Type", ac.t || "—"],
      [isZh ? "注册号" : "Reg", ac.r || "—"],
      [
        isZh ? "高度" : "Altitude",
        ac.alt_baro === "ground"
          ? isZh ? "地面" : "Ground"
          : typeof ac.alt_baro === "number"
            ? `${ac.alt_baro.toLocaleString()} ft`
            : "—",
      ],
      [isZh ? "速度" : "Speed", typeof ac.gs === "number" ? `${Math.round(ac.gs)} kt` : "—"],
      [isZh ? "航向" : "Track", typeof ac.track === "number" ? `${Math.round(ac.track)}°` : "—"],
      /* 【2026-10-28 新增】垂直速度和应答机 */
      [
        isZh ? "垂直速度" : "Vert rate",
        typeof ac.baro_rate === "number"
          ? `${ac.baro_rate > 0 ? "↑" : ac.baro_rate < 0 ? "↓" : ""}${Math.abs(ac.baro_rate)} ft/min`
          : "—",
      ],
      [isZh ? "应答机" : "Squawk", ac.squawk || "—"],
    ];
    const body = rows
      .map(([k, v]) => `<div style="display:flex;justify-content:space-between;gap:12px"><span style="opacity:.65">${k}</span><span>${esc(v)}</span></div>`)
      .join("");
    /* 照片区域：占位盒子，弹窗打开后由 loadPhoto() 填内容 */
    return `<div style="width:260px;font-size:13px;line-height:1.7"><div style="font-weight:600;margin-bottom:2px">${esc((ac.flight || "").trim() || ac.hex)}</div><div id="ph-${esc(ac.hex)}" style="margin:6px 0;color:#94a3b8">${isZh ? "照片加载中…" : "Loading photo…"}</div>${body}</div>`;
  };

  /* 【2026-10-28 新增】把查到的照片填进弹窗；弹窗已关就静默放弃 */
  const renderPhoto = (hex: string, photo: PhotoInfo) => {
    const box = document.getElementById(`ph-${hex}`);
    if (!box) return;
    if (!photo) {
      box.textContent = langRef.current ? "暂无实拍照片" : "No photo available";
      return;
    }
    box.innerHTML =
      `<a href="${esc(photo.link)}" target="_blank" rel="noreferrer">` +
      `<img src="${esc(photo.src)}" alt="" style="width:100%;border-radius:6px;display:block"/></a>` +
      `<div style="font-size:11px;color:#94a3b8;margin-top:2px">© ${esc(photo.photographer)} / planespotters.net</div>`;
  };

  /* 【2026-10-28 新增】懒加载照片：只在弹窗打开时去查一次 */
  const loadPhoto = async (hex: string) => {
    const cached = photoCacheRef.current.get(hex);
    if (cached !== undefined) {
      renderPhoto(hex, cached);
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/api/photo?hex=${encodeURIComponent(hex)}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`photo api ${res.status}`);
      const data = (await res.json()) as { photo?: PhotoInfo };
      const photo = data.photo && data.photo.src ? data.photo : null;
      photoCacheRef.current.set(hex, photo);
      renderPhoto(hex, photo);
    } catch {
      renderPhoto(hex, null);
    }
  };

  /* 【2026-10-28 新增】航迹推算：每 0.5 秒把每架飞机沿自己的航向、按地速往前挪一点 */
  const interpolate = useCallback(() => {
    const now = Date.now();
    for (const entry of markersRef.current.values()) {
      /* 地面滑行或低速的不推，避免停机坪上的飞机乱飘 */
      if (entry.onGround || entry.gs < 30) continue;
      const dtHours = (now - entry.baseAt) / 3_600_000;
      if (dtHours <= 0) continue;
      const distNm = entry.gs * dtHours;
      const rad = (entry.track * Math.PI) / 180;
      const dLat = (distNm * Math.cos(rad)) / 60;
      const cosLat = Math.cos((entry.lat * Math.PI) / 180);
      const dLon = Math.abs(cosLat) < 1e-6 ? 0 : (distNm * Math.sin(rad)) / (60 * cosLat);
      entry.marker.setLatLng([entry.lat + dLat, entry.lon + dLon]);
    }
  }, []);

  const planeIcon = (track: number, onGround: boolean): unknown => {
    const L = leafletRef.current;
    if (!L) return null;
    const color = onGround ? "#94a3b8" : "#2563eb";
    /* 【2026-10-28 修改】换成客机侧影（机头朝正北），CSS 顺时针旋转 = 航向角 */
    return L.divIcon({
      className: "air-radar-plane",
      html: `<svg viewBox="0 0 24 24" width="22" height="22" style="display:block;transform:rotate(${Math.round(track)}deg);filter:drop-shadow(0 0 2px rgba(255,255,255,.8))"><path fill="${color}" stroke="#fff" stroke-width="0.8" d="M12 1.6c.5 0 .9.3 1.1.9l.9 3.2c.1.6.2 1.5.2 2.3v1.9l6.9 4.1c.4.2.6.5.6 1v1.4c0 .4-.4.6-.8.4l-7.3-2.6v3.2l2.1 1.6c.2.2.4.5.4.8v1c0 .4-.4.6-.7.4l-3.4-1-3.4 1c-.3.2-.7 0-.7-.4v-1c0-.3.2-.6.4-.8l2.1-1.6v-3.2l-7.3 2.6c-.4.2-.8 0-.8-.4v-1.4c0-.5.2-.8.6-1l6.9-4.1V8c0-.8.1-1.7.2-2.3l.9-3.2c.2-.6.6-.9 1.1-.9z"/></svg>`,
      iconSize: [22, 22],
      iconAnchor: [11, 11],
    });
  };

  const refresh = useCallback(async () => {
    const map = mapRef.current;
    const L = leafletRef.current;
    if (!map || !L || inFlightRef.current) return;
    inFlightRef.current = true;
    setSpinning(true);
    try {
      const { lat, lng } = map.getCenter();
      const radius = radiusForZoom(map.getZoom());
      /* 虚线圈跟着查询走：中心 = 视野中心，半径 = 查询半径（海里 → 米） */
      circleRef.current?.setLatLng([lat, lng]).setRadius(radius * 1852);
      setRadiusNm(radius);
      const list = await fetchAircraft(lat, lng, radius);
      const now = Date.now();
      let shown = 0;
      for (const ac of list) {
        if (typeof ac.lat !== "number" || typeof ac.lon !== "number") continue;
        shown += 1;
        const onGround = ac.alt_baro === "ground";
        const existing = markersRef.current.get(ac.hex);
        if (existing) {
          /* 新数据落地：推算基准点重置为这次的真实位置 */
          existing.lat = ac.lat;
          existing.lon = ac.lon;
          existing.track = ac.track ?? 0;
          existing.gs = typeof ac.gs === "number" ? ac.gs : 0;
          existing.onGround = onGround;
          existing.baseAt = now;
          existing.marker.setLatLng([ac.lat, ac.lon]);
          existing.marker.setIcon(planeIcon(ac.track ?? 0, onGround));
          existing.marker.getPopup()?.setContent(popupHtml(ac));
          /* setContent 会把照片盒子重置回"加载中"，若弹窗开着且照片已缓存就补回去 */
          const cachedPhoto = photoCacheRef.current.get(ac.hex);
          if (cachedPhoto !== undefined) renderPhoto(ac.hex, cachedPhoto);
          existing.seenAt = now;
        } else {
          const marker = L.marker([ac.lat, ac.lon], {
            icon: planeIcon(ac.track ?? 0, onGround),
          })
            .addTo(map)
            .bindPopup(popupHtml(ac));
          /* 【2026-10-28 新增】弹窗每次打开都触发；查过有缓存，开销可忽略 */
          marker.on("popupopen", () => void loadPhoto(ac.hex));
          markersRef.current.set(ac.hex, {
            marker,
            seenAt: now,
            lat: ac.lat,
            lon: ac.lon,
            track: ac.track ?? 0,
            gs: typeof ac.gs === "number" ? ac.gs : 0,
            onGround,
            baseAt: now,
          });
        }
      }
      /* 清掉飞出范围或消失超过 30 秒的 */
      for (const [hex, entry] of markersRef.current) {
        if (now - entry.seenAt > STALE_MS) {
          map.removeLayer(entry.marker);
          markersRef.current.delete(hex);
        }
      }
      setCount(shown);
      setUpdatedAt(now);
      setFailed(null);
    } catch {
      setFailed(zh ? "数据接口暂时不可用，稍后会自动重试。" : "Data feed unavailable; will retry automatically.");
    } finally {
      inFlightRef.current = false;
      setSpinning(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zh]);

  /* 初始化地图 + 定时刷新，只跑一次 */
  useEffect(() => {
    const box = mapBoxRef.current;
    if (!box || mapRef.current) return;
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | undefined;
    let ticker: ReturnType<typeof setInterval> | undefined;

    (async () => {
      try {
        const L = await loadLeaflet();
        if (cancelled || !mapBoxRef.current) return;
        leafletRef.current = L;
        const map = L.map(mapBoxRef.current, {
          center: DEFAULT_CENTER,
          zoom: DEFAULT_ZOOM,
          minZoom: 3,
          maxZoom: 16,
          scrollWheelZoom: true,
          worldCopyJump: true,
        });
        L.tileLayer(TILE_URL, {
          subdomains: "1234",
          maxZoom: 18,
          attribution: "© 高德地图 | 航班数据 © adsb.lol",
        }).addTo(map);
        /* 【2026-10-28 新增】初始覆盖圈，之后每次刷新在 refresh() 里挪 */
        circleRef.current = L.circle(DEFAULT_CENTER, {
          radius: radiusForZoom(DEFAULT_ZOOM) * 1852,
          color: "#2563eb",
          weight: 1,
          opacity: 0.5,
          dashArray: "4 4",
          fillColor: "#2563eb",
          fillOpacity: 0.04,
        }).addTo(map);
        map.on("moveend", () => void refresh());
        mapRef.current = map;
        if (!cancelled) setReady(true);
        window.setTimeout(() => mapRef.current?.invalidateSize(), 150);
        void refresh();
        timer = setInterval(() => void refresh(), REFRESH_MS);
        /* 【2026-10-28 新增】平滑移动推算器 */
        ticker = setInterval(interpolate, 500);
      } catch {
        if (!cancelled) setFailed(zh ? "地图加载失败。" : "Failed to load the map.");
      }
    })();

    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
      if (ticker) clearInterval(ticker);
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
        circleRef.current = null;
        markersRef.current.clear();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const timeText = updatedAt
    ? new Date(updatedAt).toLocaleTimeString(zh ? "zh-CN" : "en-US", { hour12: false })
    : "—";

  return (
    <article>
      <PageHeader
        title={zh ? "飞机雷达" : "Flight radar"}
        lede={
          zh
            ? "实时查看附近空域的飞机，数据来自公开的 ADS-B 接收网络。拖动或缩放地图会自动查询当前视野。"
            : "Live air traffic near the current map view, from a public ADS-B receiver network. Pan or zoom to query another area."
        }
      />

      <div className="mt-8">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-muted-foreground">
          <span>
            {zh ? "视野内飞机" : "In view"}：<strong className="text-foreground">{count}</strong>
            {/* 【2026-10-28 新增】顺带显示查询半径，解释"为什么只有这些" */}
            {radiusNm > 0
              ? zh
                ? `（虚线圈范围：半径约 ${Math.round(radiusNm * 1.852)} 公里）`
                : ` (dashed circle, radius ~${Math.round(radiusNm * 1.852)} km)`
              : null}
          </span>
          <span>
            {zh ? "更新于" : "Updated"} {timeText}
          </span>
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={!ready || spinning}
            className="inline-flex items-center gap-1 text-primary underline underline-offset-4 hover:text-link-hover disabled:opacity-50"
          >
            <RefreshCw className={cn("size-3.5", spinning && "animate-spin")} aria-hidden="true" />
            {zh ? "立即刷新" : "Refresh now"}
          </button>
        </div>

        <div className="relative mt-3 h-[420px] w-full overflow-hidden rounded-xl border border-border bg-muted sm:h-[520px]">
          <div ref={mapBoxRef} className="absolute inset-0" />
          {!ready && !failed ? (
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-sm text-muted-foreground">
              {zh ? "地图加载中…" : "Loading map…"}
            </div>
          ) : null}
        </div>

        {failed ? (
          <p className="mt-3 text-sm text-muted-foreground">{failed}</p>
        ) : null}

        <p className="mt-3 text-sm leading-6 text-muted-foreground">
          {zh ? (
            <>
              数据来自{" "}
              <a
                className="text-primary underline underline-offset-4 hover:text-link-hover"
                href="https://adsb.lol/"
                target="_blank"
                rel="noreferrer"
              >
                adsb.lol
              </a>
              ，由全球志愿者架设的 ADS-B 接收机贡献，经本站服务器中转。位置会有几秒到几十秒的延迟；覆盖范围外或低空飞行的飞机可能看不到。
            </>
          ) : (
            <>
              Data from{" "}
              <a
                className="text-primary underline underline-offset-4 hover:text-link-hover"
                href="https://adsb.lol/"
                target="_blank"
                rel="noreferrer"
              >
                adsb.lol
              </a>
              , crowdsourced from volunteer ADS-B receivers worldwide and relayed by this site&apos;s own server. Positions lag a few seconds; aircraft outside receiver coverage or at low altitude may not appear.
            </>
          )}
        </p>
      </div>
    </article>
  );
}
