"use client";

import { useEffect, useState, type ComponentType, type ReactNode } from "react";
import {
  Cloud,
  CloudDrizzle,
  CloudFog,
  CloudLightning,
  CloudRain,
  CloudSnow,
  CloudSun,
  Sun,
} from "lucide-react";
import { useSite } from "@/components/site-provider";
import type { Lang } from "@/content/profile";
import { fetchWithTimeout } from "@/lib/fetch-timeout";
import { cn } from "@/lib/utils";

/**
 * Amap (高德) Web 服务 key. Set NEXT_PUBLIC_AMAP_KEY at build time to use the
 * domestic source for both the IP lookup and the forecast. Left empty, the
 * component falls back to open-meteo, which needs no key but lives abroad.
 * The key is public by design here: it ships in the client bundle either way.
 */
const AMAP_KEY = (process.env.NEXT_PUBLIC_AMAP_KEY || "").trim();

/** Weather condition families. Both providers map onto this, the UI reads it. */
type Sky =
  | "clear"
  | "partly"
  | "cloud"
  | "fog"
  | "drizzle"
  | "rain"
  | "snow"
  | "storm";

type Day = { date: string; sky: Sky; max: number; min: number };

type Forecast = {
  temp: number;
  humidity: number;
  sky: Sky;
  days: Day[];
};

type Coords = { latitude: number; longitude: number };

type Place = { city: string; lines: string[]; query: string };

type Located = {
  country: string;
  region: string;
  city: string;
  district: string;
  latitude?: number;
  longitude?: number;
  /** Amap's district code, which is what its weather endpoint expects. */
  adcode?: string;
  /** Names are already in Chinese, from the visitor's IP record. */
  chinese: boolean;
};

type SkyGlyph = ComponentType<{ className?: string; strokeWidth?: number }>;

const SKY_ICONS: Record<Sky, SkyGlyph> = {
  clear: Sun,
  partly: CloudSun,
  cloud: Cloud,
  fog: CloudFog,
  drizzle: CloudDrizzle,
  rain: CloudRain,
  snow: CloudSnow,
  storm: CloudLightning,
};

const SKY_NAMES: Record<Sky, [string, string]> = {
  clear: ["晴", "Clear"],
  partly: ["多云", "Partly cloudy"],
  cloud: ["阴", "Overcast"],
  fog: ["雾", "Fog"],
  drizzle: ["小雨", "Drizzle"],
  rain: ["雨", "Rain"],
  snow: ["雪", "Snow"],
  storm: ["雷雨", "Thunderstorm"],
};

function simplify(name: string) {
  const traditional: Record<string, string> = {
    區: "区",
    縣: "县",
    國: "国",
    東: "东",
    門: "门",
    島: "岛",
    臺: "台",
    萬: "万",
  };
  return name.replace(/[區縣國東門島臺萬]/g, (char) => traditional[char] ?? char);
}

function cityLabel(name: string) {
  const trimmed = simplify(name.trim());
  const short = trimmed.replace(/市$/, "").replace(/\s+city$/i, "").trim();
  return short || trimmed;
}

function addressLines(names: string[]) {
  const lines: string[] = [];
  for (const name of names) {
    const trimmed = simplify(name.trim()).replace(/ Sheng$/, "");
    if (!trimmed || lines[lines.length - 1] === trimmed) continue;
    lines.push(trimmed);
  }
  return lines;
}

function regionName(name: string) {
  if (!name || /省|市|自治区|特别行政区|区$/.test(name)) return name;
  if (["北京", "上海", "天津", "重庆"].includes(name)) return `${name}市`;
  if (["香港", "澳门"].includes(name)) return name;
  return `${name}省`;
}

function cityWithSuffix(name: string) {
  if (!name || /[市州盟县区]$/.test(name)) return name;
  if (["香港", "澳门"].includes(name)) return name;
  return `${name}市`;
}

function zhAddress(ip: Located) {
  return addressLines([
    ip.country,
    regionName(ip.region),
    cityWithSuffix(ip.city),
    ip.district,
  ]);
}

function addressQuery(lines: string[], lang: Lang) {
  return lang === "zh" ? lines.join("") : lines.join(", ");
}

function mapsHref(query: string, lang: Lang) {
  // Google Maps is the better map for readers outside China; for Chinese
  // readers it is simply unreachable, so they get Amap's web search instead.
  const base =
    lang === "zh"
      ? "https://www.amap.com/search"
      : "https://www.google.com/maps/search/";
  return `${base}?query=${encodeURIComponent(query)}`;
}

/**
 * Amap IP lookup. Returns province/city plus the adcode the weather endpoint
 * needs. An overseas address comes back as empty arrays rather than strings,
 * which is why every field goes through a type guard.
 */
async function readAmapIp(): Promise<Located | null> {
  try {
    const response = await fetchWithTimeout(
      `https://restapi.amap.com/v3/ip?key=${encodeURIComponent(AMAP_KEY)}`,
      {},
      4000,
    );
    if (!response.ok) return null;
    const data = await response.json();
    if (data?.status !== "1") return null;
    const province = typeof data.province === "string" ? data.province : "";
    const city = typeof data.city === "string" ? data.city : "";
    if (!city) return null;
    return {
      country: "中国",
      region: province,
      city,
      district: "",
      adcode: typeof data.adcode === "string" ? data.adcode : undefined,
      chinese: true,
    };
  } catch {
    return null;
  }
}

/**
 * Domestic lookup: returns Chinese province/city/district but no coordinates.
 * Measured at ~2s from a mainland connection.
 */
async function readChineseIp(): Promise<Located | null> {
  if (AMAP_KEY) {
    const amap = await readAmapIp();
    if (amap?.adcode) return amap;
  }
  try {
    const response = await fetchWithTimeout("https://myip.ipip.net/json", {}, 4000);
    if (!response.ok) return null;
    const data = await response.json();
    const location = data?.data?.location;
    if (data?.ret !== "ok" || !Array.isArray(location) || !location[2]) {
      return null;
    }
    return {
      country: String(location[0] || ""),
      region: String(location[1] || ""),
      city: String(location[2] || ""),
      district: String(location[3] || ""),
      chinese: true,
    };
  } catch {
    return null;
  }
}

/**
 * Backup lookup. It carries latitude/longitude, which is the part that matters:
 * with coordinates in hand the city-name geocode below can be skipped entirely,
 * and that single call used to cost more than everything else combined.
 */
async function readCoords(): Promise<Located | null> {
  try {
    const response = await fetchWithTimeout("https://api.ip.sb/geoip", {}, 4000);
    if (!response.ok) return null;
    const data = await response.json();
    const latitude = Number(data.latitude);
    const longitude = Number(data.longitude);
    if (!data?.city) return null;
    return {
      country: String(data.country || ""),
      region: String(data.region || ""),
      city: String(data.city),
      district: "",
      latitude: Number.isFinite(latitude) ? latitude : undefined,
      longitude: Number.isFinite(longitude) ? longitude : undefined,
      chinese: false,
    };
  } catch {
    return null;
  }
}

/** WMO weather code (open-meteo) → condition family. */
function skyFromCode(code: number): Sky {
  if (code === 0) return "clear";
  if (code <= 2) return "partly";
  if (code === 3) return "cloud";
  if (code === 45 || code === 48) return "fog";
  if (code >= 51 && code <= 57) return "drizzle";
  if ((code >= 71 && code <= 77) || code === 85 || code === 86) return "snow";
  if (code >= 95) return "storm";
  if (code >= 61) return "rain";
  return "cloud";
}

/** Amap answers in Chinese prose ("小雨", "多云"), so match on keywords. */
function skyFromText(text: string): Sky {
  if (/雷/.test(text)) return "storm";
  if (/雪|冰雹|霰/.test(text)) return "snow";
  if (/雾|霾|沙尘|浮尘/.test(text)) return "fog";
  if (/毛毛|细雨|小雨/.test(text)) return "drizzle";
  if (/雨/.test(text)) return "rain";
  if (/阴/.test(text)) return "cloud";
  if (/云/.test(text)) return "partly";
  if (/晴/.test(text)) return "clear";
  return "partly";
}

/**
 * Amap forecast. Two calls: the live reading carries the current temperature
 * and humidity, the forecast carries daily highs and lows. Amap publishes four
 * days rather than seven, so the strip renders however many it returns.
 */
async function readAmapWeather(adcode: string): Promise<Forecast | null> {
  const base =
    `https://restapi.amap.com/v3/weather/weatherInfo?key=${encodeURIComponent(AMAP_KEY)}` +
    `&city=${encodeURIComponent(adcode)}`;
  try {
    const [liveRes, castRes] = await Promise.all([
      fetchWithTimeout(`${base}&extensions=base`, {}, 6000),
      fetchWithTimeout(`${base}&extensions=all`, {}, 6000),
    ]);
    if (!liveRes.ok || !castRes.ok) return null;
    const live = await liveRes.json();
    const cast = await castRes.json();
    const now = live?.lives?.[0];
    const casts = cast?.forecasts?.[0]?.casts;
    if (!now || !Array.isArray(casts) || casts.length === 0) return null;

    return {
      temp: Math.round(Number(now.temperature) || 0),
      humidity: Math.round(Number(now.humidity) || 0),
      sky: skyFromText(String(now.weather || "")),
      days: casts.map(
        (item: {
          date?: string;
          dayweather?: string;
          daytemp?: string;
          nighttemp?: string;
        }) => ({
          date: String(item.date || ""),
          sky: skyFromText(String(item.dayweather || "")),
          max: Math.round(Number(item.daytemp) || 0),
          min: Math.round(Number(item.nighttemp) || 0),
        }),
      ),
    };
  } catch {
    return null;
  }
}

async function geocodeCity(city: string, region: string) {
  const url = new URL("https://geocoding-api.open-meteo.com/v1/search");
  url.searchParams.set("name", city);
  url.searchParams.set("count", "5");
  url.searchParams.set("language", "zh");
  url.searchParams.set("format", "json");
  const response = await fetchWithTimeout(url, {}, 7000);
  if (!response.ok) return null;
  const data = await response.json();
  const results: Array<{ admin1?: string; latitude: number; longitude: number }> =
    data?.results ?? [];
  const match =
    results.find((item) => region && (item.admin1 || "").includes(region.slice(0, 2))) ??
    results[0];
  if (!match) return null;
  return { latitude: match.latitude, longitude: match.longitude };
}

async function reverseCity(coords: Coords, lang: Lang): Promise<Place | null> {
  const url = new URL("https://api.bigdatacloud.net/data/reverse-geocode-client");
  url.searchParams.set("latitude", String(coords.latitude));
  url.searchParams.set("longitude", String(coords.longitude));
  url.searchParams.set("localityLanguage", lang === "zh" ? "zh" : "en");
  const response = await fetchWithTimeout(url, {}, 7000);
  if (!response.ok) return null;
  const data = await response.json();
  const admin = Array.isArray(data?.localityInfo?.administrative)
    ? data.localityInfo.administrative.map((item: { name?: string }) => item?.name ?? "")
    : [];
  const lines = addressLines(admin);
  const city = cityLabel(typeof data?.city === "string" ? data.city : "");
  if (!city && !lines.length) return null;
  return {
    city: city || cityLabel(lines[lines.length - 1] ?? ""),
    lines,
    query: addressQuery(lines, lang),
  };
}

function pad(value: number) {
  return String(value).padStart(2, "0");
}

function SkyIcon({
  sky,
  className,
  strokeWidth,
}: {
  sky: Sky;
  className?: string;
  strokeWidth?: number;
}) {
  const Icon = SKY_ICONS[sky];
  return <Icon className={className} strokeWidth={strokeWidth} />;
}

function weatherName(sky: Sky, lang: Lang) {
  const pair = SKY_NAMES[sky];
  return lang === "zh" ? pair[0] : pair[1];
}

function clockOf(now: Date, lang: Lang) {
  const hours = pad(now.getHours());
  const minutes = pad(now.getMinutes());
  const seconds = pad(now.getSeconds());
  const date =
    lang === "zh"
      ? `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日`
      : new Intl.DateTimeFormat("en", {
          year: "numeric",
          month: "long",
          day: "numeric",
        }).format(now);
  const weekday =
    lang === "zh"
      ? `星期${"日一二三四五六"[now.getDay()]}`
      : new Intl.DateTimeFormat("en", { weekday: "long" }).format(now);
  return { hours, minutes, seconds, date, weekday };
}

function dayLabel(date: string, lang: Lang) {
  const [year, month, day] = date.split("-").map(Number);
  const value = new Date(Date.UTC(year, (month || 1) - 1, day || 1));
  const index = value.getUTCDay();
  if (lang === "zh") return `周${"日一二三四五六"[index]}`;
  return ["S", "M", "T", "W", "T", "F", "S"][index];
}

function Popover({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className="status-pop pointer-events-none absolute top-full right-0 z-50 pt-2">
      <div
        className={cn(
          "status-card origin-top-right rounded-lg border border-border bg-background p-3 text-left text-foreground shadow-lg",
          className,
        )}
      >
        {children}
      </div>
    </div>
  );
}

const controlClass =
  "inline-flex h-8 items-center rounded-md px-1.5 text-sm leading-none text-muted-foreground hover:bg-muted hover:text-foreground";

export function HeaderStatus() {
  const { lang } = useSite();
  const [now, setNow] = useState<Date | null>(null);
  const [coords, setCoords] = useState<Coords | null>(null);
  const [ip, setIp] = useState<Located | null>(null);
  const [place, setPlace] = useState<Place | null>(null);
  const [forecast, setForecast] = useState<Forecast | null>(null);

  useEffect(() => {
    const tick = () => setNow(new Date());
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function locate() {
      // Amap answers for an adcode, so neither the coordinate lookup nor the
      // city-name geocode below is needed when it is configured.
      const [zh, geo] = await Promise.all([
        readChineseIp(),
        AMAP_KEY ? Promise.resolve(null) : readCoords(),
      ]);
      if (cancelled) return;

      const located = zh ?? geo;
      if (!located) return;
      setIp(located);

      if (AMAP_KEY) return;

      if (geo?.latitude != null && geo.longitude != null) {
        setCoords({ latitude: geo.latitude, longitude: geo.longitude });
        return;
      }

      if (!located.city) return;
      try {
        const point = await geocodeCity(located.city, located.region);
        if (!cancelled && point) setCoords(point);
      } catch {
        // The city can still show when the forecast coordinates are missing.
      }
    }

    locate();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!ip) return;
    let cancelled = false;

    const located = ip;
    async function namePlace() {
      const here = coords;
      // The domestic lookup already returns Chinese names. Re-resolving those
      // through a foreign reverse-geocoder buys nothing and costs a round trip.
      const skipLookup = lang === "zh" && located.chinese;
      if (here && !skipLookup) {
        try {
          const named = await reverseCity(here, lang);
          if (!cancelled && named) {
            setPlace(named);
            return;
          }
        } catch {
          // Fall through to the IP record's own names.
        }
      }
      const city = cityLabel(located.city);
      const lines = located.chinese
        ? zhAddress(located)
        : addressLines([
            located.country,
            located.region,
            cityWithSuffix(located.city),
            located.district,
          ]);
      if (!cancelled && (city || lines.length)) {
        setPlace({
          city: city || lines[lines.length - 1],
          lines,
          query: addressQuery(lines, lang),
        });
      }
    }

    namePlace();
    return () => {
      cancelled = true;
    };
  }, [ip, lang, coords]);

  const adcode = AMAP_KEY ? (ip?.adcode ?? "") : "";

  useEffect(() => {
    // Amap needs only the district code; the fallback needs latitude/longitude.
    // Exactly one of the two is ever set, so a single effect serves both.
    if (AMAP_KEY) {
      if (!adcode) return;
    } else if (!coords) {
      return;
    }
    let cancelled = false;

    async function load() {
      if (AMAP_KEY) {
        const reading = await readAmapWeather(adcode);
        if (!cancelled && reading) setForecast(reading);
        return;
      }
      const here = coords;
      if (!here) return;
      try {
        const url = new URL("https://api.open-meteo.com/v1/forecast");
        url.searchParams.set("latitude", String(here.latitude));
        url.searchParams.set("longitude", String(here.longitude));
        url.searchParams.set(
          "current",
          "temperature_2m,relative_humidity_2m,weather_code",
        );
        url.searchParams.set(
          "daily",
          "weather_code,temperature_2m_max,temperature_2m_min",
        );
        url.searchParams.set("timezone", "auto");
        url.searchParams.set("forecast_days", "7");
        const response = await fetchWithTimeout(url, {}, 9000);
        if (!response.ok) return;
        const data = await response.json();
        if (cancelled) return;
        setForecast({
          temp: Math.round(data.current.temperature_2m),
          humidity: Math.round(data.current.relative_humidity_2m),
          sky: skyFromCode(data.current.weather_code),
          days: data.daily.time.map((date: string, index: number) => ({
            date,
            sky: skyFromCode(data.daily.weather_code[index]),
            max: Math.round(data.daily.temperature_2m_max[index]),
            min: Math.round(data.daily.temperature_2m_min[index]),
          })),
        });
      } catch {
        // Keep the last reading. The clock still works if the forecast is unreachable.
      }
    }

    load();
    const timer = window.setInterval(load, 30 * 60 * 1000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [adcode, coords]);

  const clock = now ? clockOf(now, lang) : null;
  const days = forecast?.days ?? [];

  return (
    <div className="flex items-center gap-0.5 border-l border-border pl-1">
      <div className="group relative flex items-center">
        <button
          type="button"
          className={cn(controlClass, "tabular-nums")}
          aria-label={
            clock
              ? lang === "zh"
                ? `现在 ${clock.hours}:${clock.minutes}:${clock.seconds}，${clock.date} ${clock.weekday}`
                : `Now ${clock.hours}:${clock.minutes}:${clock.seconds}, ${clock.date}, ${clock.weekday}`
              : lang === "zh"
                ? "时间"
                : "Time"
          }
        >
          {clock ? `${clock.hours}:${clock.minutes}` : "--:--"}
        </button>
        <Popover className="w-44">
          <p className="status-line font-serif text-2xl tabular-nums tracking-tight">
            {clock ? (
              <>
                {clock.hours}:{clock.minutes}:
                <span key={clock.seconds} className="second-tick">
                  {clock.seconds}
                </span>
              </>
            ) : (
              "--:--:--"
            )}
          </p>
          <p
            className="status-line mt-1 text-sm text-muted-foreground"
            style={{ animationDelay: "60ms" }}
          >
            {clock ? clock.date : ""}
          </p>
          <p
            className="status-line text-sm text-muted-foreground"
            style={{ animationDelay: "110ms" }}
          >
            {clock ? clock.weekday : ""}
          </p>
        </Popover>
      </div>

      <div className="group relative flex items-center">
        <button
          type="button"
          className={cn(controlClass, "gap-1.5 tabular-nums")}
          aria-label={
            forecast
              ? lang === "zh"
                ? `${place?.city ? `${place.city} ` : ""}${forecast.temp}度，湿度 ${forecast.humidity}%，${weatherName(forecast.sky, lang)}`
                : `${place?.city ? `${place.city} ` : ""}${forecast.temp} degrees, humidity ${forecast.humidity} percent, ${weatherName(forecast.sky, lang)}`
              : lang === "zh"
                ? "天气"
                : "Weather"
          }
        >
          <SkyIcon
            sky={forecast?.sky ?? "cloud"}
            className="size-4 shrink-0"
            strokeWidth={1.75}
          />
          <span className="inline-flex items-start">
            <span>{forecast ? forecast.temp : "--"}</span>
            <span className="mt-px text-[0.7em] leading-none">°</span>
          </span>
        </button>
        <Popover className="w-[17.5rem]">
          <p className="status-line text-xs tracking-wide text-muted-foreground">
            {place?.city ?? ""}
          </p>
          <p className="status-line mt-1 flex items-baseline gap-2" style={{ animationDelay: "40ms" }}>
            <span className="font-serif text-2xl tabular-nums tracking-tight">
              {forecast ? `${forecast.temp}°` : "--°"}
            </span>
            <span className="text-sm text-muted-foreground">
              {forecast
                ? lang === "zh"
                  ? `湿度 ${forecast.humidity}%`
                  : `${forecast.humidity}% humidity`
                : lang === "zh"
                  ? "湿度 --"
                  : "-- humidity"}
            </span>
          </p>
          <p
            className="status-line mt-3 text-xs text-muted-foreground"
            style={{ animationDelay: "90ms" }}
          >
            {lang === "zh" ? `未来${days.length}天` : `Next ${days.length} days`}
          </p>
          <ul
            className="mt-2 grid gap-1"
            style={{
              gridTemplateColumns: `repeat(${Math.max(days.length, 1)}, minmax(0, 1fr))`,
            }}
          >
            {days.map((day, index) => (
              <li
                key={day.date}
                title={weatherName(day.sky, lang)}
                className="status-line flex flex-col items-center gap-0.5 text-center"
                style={{ animationDelay: `${140 + index * 35}ms` }}
              >
                <span className="text-[11px] text-muted-foreground">
                  {dayLabel(day.date, lang)}
                </span>
                <SkyIcon sky={day.sky} className="my-0.5 size-4" />
                <span className="text-xs tabular-nums">{day.max}°</span>
                <span className="text-[11px] tabular-nums text-muted-foreground">
                  {day.min}°
                </span>
              </li>
            ))}
          </ul>
        </Popover>
      </div>

      {place?.city ? (
        <div className="group relative flex items-center">
          <a
            href={mapsHref(place.query, lang)}
            target="_blank"
            rel="noreferrer"
            className={controlClass}
            aria-label={
              lang === "zh"
                ? `在谷歌地图打开 ${place.query}`
                : `Open ${place.query} in Google Maps`
            }
          >
            {place.city}
          </a>
          <Popover className="w-max max-w-64 min-w-36">
            {place.lines.map((line, index) => {
              const finest = index === place.lines.length - 1;
              return (
                <p
                  key={`${line}-${index}`}
                  className={cn(
                    "status-line",
                    finest
                      ? "text-sm font-medium text-foreground"
                      : "text-sm text-muted-foreground",
                    index > 0 && "mt-0.5",
                  )}
                  style={{ animationDelay: `${index * 55}ms` }}
                >
                  {line}
                </p>
              );
            })}
          </Popover>
        </div>
      ) : null}
    </div>
  );
}
