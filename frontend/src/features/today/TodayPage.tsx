import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  ChevronDown,
  Info,
  RefreshCw,
  ShieldCheck,
  WifiOff,
} from "lucide-react";
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Link } from "react-router";

import { AqiCategoryChip, CATEGORY_LABELS } from "../../components/AqiCategoryChip";
import {
  ApiError,
  fetchAir,
  fetchAirForecast,
  fetchHousehold,
  type MemberInput,
} from "../../lib/api";
import { formatHoursOld, formatIstTimeWithZone } from "../../lib/datetime";
import { WhatDoesThisMeanSheet } from "./WhatDoesThisMeanSheet";

const ForecastSection = lazy(() => import("./ForecastSection"));

const POLLUTANT_LABELS: Record<string, string> = {
  pm25: "PM2.5",
  pm10: "PM10",
  no2: "NO₂",
  o3: "O₃",
  co: "CO",
  so2: "SO₂",
};

function sensitiveReasonText(members: MemberInput[]): string | null {
  const parts: string[] = [];
  if (members.some((m) => m.kind === "child_u12" && m.count > 0)) {
    parts.push("a child");
  }
  if (members.some((m) => m.kind === "adult_65p" && m.count > 0)) {
    parts.push("an older adult");
  }
  if (members.some((m) => m.kind === "heart_lung" && m.count > 0)) {
    parts.push("someone with heart or lung sensitivity");
  }
  if (parts.length === 0) return null;
  const joined =
    parts.length === 1
      ? parts[0]
      : parts.length === 2
        ? `${parts[0]} and ${parts[1]}`
        : `${parts.slice(0, -1).join(", ")}, and ${parts[parts.length - 1]}`;
  return `Your household includes ${joined}, so stricter rules apply.`;
}

export default function TodayPage() {
  const [sheetOpen, setSheetOpen] = useState(false);
  const [showIndicativeNote, setShowIndicativeNote] = useState(false);
  const [isOnline, setIsOnline] = useState(() =>
    typeof navigator !== "undefined" ? navigator.onLine : true
  );
  const meaningBtnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const goOnline = () => setIsOnline(true);
    const goOffline = () => setIsOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, []);

  const householdQuery = useQuery({
    queryKey: ["household"],
    queryFn: fetchHousehold,
    retry: false,
  });

  const primaryLocation = householdQuery.data?.location;

  const airQuery = useQuery({
    queryKey: ["air", primaryLocation?.lat, primaryLocation?.lon],
    queryFn: () => {
      if (!primaryLocation) throw new Error("Location missing");
      return fetchAir(primaryLocation.lat, primaryLocation.lon);
    },
    enabled: Boolean(primaryLocation),
    refetchInterval: 30 * 60 * 1000,
  });

  const forecastQuery = useQuery({
    queryKey: ["air", "forecast", primaryLocation?.lat, primaryLocation?.lon],
    queryFn: () => {
      if (!primaryLocation) throw new Error("Location missing");
      return fetchAirForecast(primaryLocation.lat, primaryLocation.lon, 12);
    },
    enabled: Boolean(primaryLocation),
    refetchInterval: 30 * 60 * 1000,
  });

  if (householdQuery.isLoading || (primaryLocation && airQuery.isLoading && !airQuery.data)) {
    return (
      <div aria-busy="true" aria-label="Loading air quality overview" className="space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h1>Today</h1>
        </div>
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          <div className="purvai-card h-[240px] animate-pulse bg-subtle p-6 lg:col-span-7" />
          <div className="purvai-card h-[240px] animate-pulse bg-subtle p-6 lg:col-span-5" />
        </div>
      </div>
    );
  }

  const air = airQuery.data;
  const offlineWithCache = Boolean(air && (!isOnline || airQuery.isError));

  if (!air && airQuery.isError) {
    const message =
      airQuery.error instanceof ApiError
        ? airQuery.error.message
        : airQuery.error instanceof Error
          ? airQuery.error.message
          : "Unable to load air quality right now.";

    return (
      <div className="space-y-6">
        <h1>Today</h1>
        <div
          role="alert"
          className="purvai-card max-w-[720px] space-y-4 border-danger bg-danger-tint p-6 text-danger"
        >
          <div className="flex items-start gap-2">
            <AlertCircle size={18} className="mt-0.5 shrink-0" aria-hidden />
            <p className="text-sm">{message}</p>
          </div>
          <button
            type="button"
            disabled={!isOnline || airQuery.isFetching}
            onClick={() => {
              void airQuery.refetch();
            }}
            className="purvai-btn purvai-btn-primary"
          >
            <RefreshCw size={18} aria-hidden />
            <span>Retry</span>
          </button>
        </div>
      </div>
    );
  }

  if (!air || !householdQuery.data) {
    return null;
  }

  const aqiDisplay = air.aqi_is_floor ? `${air.aqi}+` : String(air.aqi);
  const categoryWord = CATEGORY_LABELS[air.category];
  const aqiAriaLabel = `${air.aqi}, ${categoryWord}, CPCB scale, ${air.source_label}`;
  const observedIst = formatIstTimeWithZone(air.observed_at);
  const sensitiveNote = sensitiveReasonText(householdQuery.data.members);

  const sourceLine =
    air.source.provider === "CPCB" && air.source.station
      ? `${air.source_label} · CPCB station · ${air.source.station} · ${air.source.distance_km} km · ${observedIst}`
      : `${air.source_label} · ${air.source.provider} · ${observedIst}`;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1>Today</h1>
        <p className="text-sm text-text-2">{householdQuery.data.location.label}</p>
      </div>

      {offlineWithCache && (
        <div
          role="status"
          className="flex items-center gap-2 rounded-[6px] border border-warning bg-warning-tint px-4 py-3 text-sm text-warning"
        >
          <WifiOff size={18} className="shrink-0" aria-hidden />
          <span>Offline, showing data from {observedIst}</span>
        </div>
      )}

      {air.stale && (
        <div
          role="status"
          className="flex items-center gap-2 rounded-[6px] border border-warning bg-warning-tint px-4 py-3 text-sm text-warning"
        >
          <AlertTriangle size={18} className="shrink-0" aria-hidden />
          <span>Data is {formatHoursOld(air.age_minutes)} old. Showing the last reading.</span>
        </div>
      )}

      {air.served_from_cache && (
        <p className="text-sm text-text-2">Showing saved data from {observedIst}</p>
      )}

      {/* Verdict Card + AQI Hero */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <section
          aria-live="polite"
          aria-labelledby="verdict-headline"
          className="purvai-verdict-hero flex flex-col justify-between space-y-5 p-6 lg:col-span-7"
        >
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs font-medium uppercase tracking-wide text-muted">
                Right now · Your household
              </span>
              <span className="rounded-full border border-border bg-surface px-2.5 py-0.5 text-xs font-medium text-text-2">
                Rule
              </span>
            </div>

            <h2 id="verdict-headline">{air.verdict.headline}</h2>

            {sensitiveNote && <p className="text-sm text-text-2">{sensitiveNote}</p>}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Link to="/plan" className="purvai-btn purvai-btn-primary">
              <span>Plan my day</span>
              <ArrowRight size={18} aria-hidden />
            </Link>

            <Link to="/ask" className="purvai-btn purvai-btn-tertiary">
              Ask about today
            </Link>

            <button
              ref={meaningBtnRef}
              type="button"
              onClick={() => setSheetOpen(true)}
              className="purvai-btn purvai-btn-ghost"
            >
              What does this mean?
            </button>
          </div>
        </section>

        <section
          aria-label={aqiAriaLabel}
          className="purvai-card flex flex-col justify-between space-y-4 p-6 lg:col-span-5"
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="aqi-hero-number text-text">{aqiDisplay}</div>
              <div className="mt-1 text-sm font-medium text-text-2">CPCB AQI</div>
            </div>

            <AqiCategoryChip category={air.category} showBar />
          </div>

          <div className="space-y-2 border-t border-border pt-4 text-sm text-text-2">
            <p>{sourceLine}</p>

            {air.indicative && (
              <div>
                <button
                  type="button"
                  aria-expanded={showIndicativeNote}
                  onClick={() => setShowIndicativeNote((prev) => !prev)}
                  className="inline-flex min-h-[44px] items-center gap-1.5 text-xs font-medium text-text-2 underline underline-offset-4"
                >
                  <Info size={14} aria-hidden />
                  <span>Indicative</span>
                </button>
                {showIndicativeNote && (
                  <p className="mt-1 rounded-[6px] bg-subtle p-2.5 text-xs text-text-2">
                    Official CPCB NAQI uses 24-hour and 8-hour averages; real-time station and
                    modelled readings cover shorter windows, so values are labelled indicative.
                  </p>
                )}
              </div>
            )}
          </div>
        </section>
      </div>

      {/* GRAP Banner */}
      {air.grap && (
        <aside
          aria-label="GRAP status"
          className="flex flex-wrap items-center justify-between gap-3 rounded-[10px] border border-border bg-info-tint px-4 py-3 text-sm text-info"
        >
          <div className="flex items-center gap-2.5">
            <Info size={18} className="shrink-0" aria-hidden />
            <span>
              GRAP Stage {air.grap.stage} is in force for Delhi NCR. (Order date:{" "}
              <span className="tabular-data">{air.grap.order_date}</span>)
            </span>
          </div>
          <a
            href={air.grap.source_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex min-h-[44px] items-center font-medium underline underline-offset-4"
          >
            CAQM notice
          </a>
        </aside>
      )}

      {/* Three Action Cards */}
      <section aria-labelledby="actions-heading" className="space-y-3">
        <h2 id="actions-heading" className="text-xl font-semibold">
          What to do right now
        </h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {air.verdict.actions.map((action) => (
            <div
              key={action.action_id}
              className="purvai-card flex flex-col justify-between gap-3 p-5"
            >
              <div className="flex items-start gap-2.5">
                <ShieldCheck size={18} className="mt-0.5 shrink-0 text-accent" aria-hidden />
                <p className="text-sm font-medium text-text">{action.text}</p>
              </div>
              <div>
                <span className="rounded-full border border-border bg-subtle px-2.5 py-0.5 text-xs font-medium text-text-2">
                  Rule
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* 12-Hour Forecast (lazy-loaded Recharts) */}
      {forecastQuery.data && (
        <Suspense
          fallback={
            <div className="purvai-card h-[340px] animate-pulse bg-subtle p-6" aria-busy="true" />
          }
        >
          <ForecastSection forecast={forecastQuery.data} />
        </Suspense>
      )}

      {/* Pollutant Details (collapsed) */}
      <details className="purvai-card p-5">
        <summary className="flex min-h-[44px] cursor-pointer list-none items-center justify-between font-heading text-base font-medium text-text">
          <span>Pollutant breakdown</span>
          <ChevronDown size={18} aria-hidden />
        </summary>
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Object.entries(air.pollutants).map(([key, reading]) => {
            const isDominant = key === air.dominant_pollutant;
            return (
              <div
                key={key}
                className="flex items-center justify-between rounded-[6px] border border-border bg-subtle px-4 py-3"
              >
                <div>
                  <div className="flex items-center gap-2 font-heading text-sm font-medium">
                    <span>{POLLUTANT_LABELS[key] ?? key.toUpperCase()}</span>
                    {isDominant && (
                      <span className="rounded-full border border-border bg-surface px-2 py-0.5 text-xs text-text-2">
                        Dominant
                      </span>
                    )}
                  </div>
                  <div className="tabular-data text-xs text-text-2">
                    {reading.value} {reading.unit}
                  </div>
                </div>
                <div className="tabular-data text-right">
                  <div className="text-xs text-muted">Sub-index</div>
                  <div className="text-base font-semibold">{reading.sub_index}</div>
                </div>
              </div>
            );
          })}
        </div>
      </details>

      <WhatDoesThisMeanSheet
        open={sheetOpen}
        currentCategory={air.category}
        onClose={() => setSheetOpen(false)}
        returnFocusRef={meaningBtnRef}
      />
    </div>
  );
}
