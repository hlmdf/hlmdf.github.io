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
import { cn } from "@/lib/utils";

type Day = { date: string; code: number; max: number; min: number };

type Forecast = {
  temp: number;
  humidity: number;
  code: number;
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
  /** Names are already in Chinese, from the visitor's IP record. */
  chinese: boolean;
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

function mapsHref(query: string) {
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
}

async function readVisitor(): Promise<Located | null> {
  try {
    const response = await fetch("https://myip.ipip.net/json");
    if (response.ok) {
      const data = await response.json();
      const location = data?.data?.location;
      if (data?.ret === "ok" && Array.isArray(location) && location[2]) {
        return {
          country: String(location[0] || ""),
          region: String(location[1] || ""),
          city: String(location[2] || ""),
          district: String(location[3] || ""),
          chinese: true,
        };
      }
    }
  } catch {
    // Try the next lookup. Some networks block this one.
  }

  try {
    const response = await fetch("https://api.ip.sb/geoip");
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

async function geocodeCity(city: string, region: string) {
  const url = new URL("https://geocoding-api.open-meteo.com/v1/search");
  url.searchParams.set("name", city);
  url.searchParams.set("count", "5");
  url.searchParams.set("language", "zh");
  url.searchParams.set("format", "json");
  const response = await fetch(url);
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
  const response = await fetch(url);
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

function weatherIcon(code: number): ComponentType<{ className?: string }> {
  if (code === 0) return Sun;
  if (code <= 2) return CloudSun;
  if (code === 3) return Cloud;
  if (code === 45 || code === 48) return CloudFog;
  if (code >= 51 && code <= 57) return CloudDrizzle;
  if ((code >= 71 && code <= 77) || code === 85 || code === 86) return CloudSnow;
  if (code >= 95) return CloudLightning;
  if (code >= 61) return CloudRain;
  return Cloud;
}

function weatherName(code: number, lang: Lang) {
  const names: Record<string, [string, string]> = {
    clear: ["晴", "Clear"],
    partly: ["多云", "Partly cloudy"],
    cloud: ["阴", "Overcast"],
    fog: ["雾", "Fog"],
    drizzle: ["小雨", "Drizzle"],
    rain: ["雨", "Rain"],
    snow: ["雪", "Snow"],
    storm: ["雷雨", "Thunderstorm"],
  };
  const key =
    code === 0
      ? "clear"
      : code <= 2
        ? "partly"
        : code === 3
          ? "cloud"
          : code === 45 || code === 48
            ? "fog"
            : code <= 57
              ? "drizzle"
              : code >= 95
                ? "storm"
                : code >= 71 && code <= 86
                  ? "snow"
                  : "rain";
  const pair = names[key];
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
      const found = await readVisitor();
      if (cancelled || !found) return;
      setIp(found);
      if (found.latitude != null && found.longitude != null) {
        setCoords({ latitude: found.latitude, longitude: found.longitude });
        return;
      }
      try {
        const point = await geocodeCity(found.city, found.region);
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
      if (here) {
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

  useEffect(() => {
    if (!coords) return;
    const here = coords;
    let cancelled = false;

    async function load() {
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
        const response = await fetch(url);
        if (!response.ok) return;
        const data = await response.json();
        if (cancelled) return;
        setForecast({
          temp: Math.round(data.current.temperature_2m),
          humidity: Math.round(data.current.relative_humidity_2m),
          code: data.current.weather_code,
          days: data.daily.time.map((date: string, index: number) => ({
            date,
            code: data.daily.weather_code[index],
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
  }, [coords]);

  const clock = now ? clockOf(now, lang) : null;
  const CurrentIcon = forecast ? weatherIcon(forecast.code) : Cloud;

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
                ? `${place?.city ? `${place.city} ` : ""}${forecast.temp}度，湿度 ${forecast.humidity}%，${weatherName(forecast.code, lang)}`
                : `${place?.city ? `${place.city} ` : ""}${forecast.temp} degrees, humidity ${forecast.humidity} percent, ${weatherName(forecast.code, lang)}`
              : lang === "zh"
                ? "天气"
                : "Weather"
          }
        >
          <CurrentIcon className="size-4 shrink-0" strokeWidth={1.75} />
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
            {lang === "zh" ? "未来七天" : "Next 7 days"}
          </p>
          <ul className="mt-2 grid grid-cols-7 gap-1">
            {(forecast?.days ?? []).map((day, index) => {
              const Icon = weatherIcon(day.code);
              return (
                <li
                  key={day.date}
                  title={weatherName(day.code, lang)}
                  className="status-line flex flex-col items-center gap-0.5 text-center"
                  style={{ animationDelay: `${140 + index * 35}ms` }}
                >
                  <span className="text-[11px] text-muted-foreground">
                    {dayLabel(day.date, lang)}
                  </span>
                  <Icon className="my-0.5 size-4" />
                  <span className="text-xs tabular-nums">{day.max}°</span>
                  <span className="text-[11px] tabular-nums text-muted-foreground">
                    {day.min}°
                  </span>
                </li>
              );
            })}
          </ul>
        </Popover>
      </div>

      {place?.city ? (
        <div className="group relative flex items-center">
          <a
            href={mapsHref(place.query)}
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
