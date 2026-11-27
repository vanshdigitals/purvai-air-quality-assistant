import { useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { CATEGORY_LABELS } from "../../components/AqiCategoryChip";
import type { AirForecastResponse } from "../../lib/api";
import { formatIstTime } from "../../lib/datetime";

interface ForecastSectionProps {
  forecast: AirForecastResponse;
}

const BANDS = [
  { y1: 0, y2: 50, fill: "var(--aqi-good)" },
  { y1: 51, y2: 100, fill: "var(--aqi-satisfactory)" },
  { y1: 101, y2: 200, fill: "var(--aqi-moderate)" },
  { y1: 201, y2: 300, fill: "var(--aqi-poor)" },
  { y1: 301, y2: 400, fill: "var(--aqi-very-poor)" },
  { y1: 401, y2: 500, fill: "var(--aqi-severe)" },
] as const;

export default function ForecastSection({ forecast }: ForecastSectionProps) {
  const [showTable, setShowTable] = useState(false);

  const chartData = forecast.hours.map((h) => ({
    timeIst: formatIstTime(h.time),
    aqi: h.aqi,
    category: CATEGORY_LABELS[h.category],
    dominant: h.dominant_pollutant.toUpperCase(),
    isFloor: h.aqi_is_floor,
  }));

  const lowestTime = formatIstTime(forecast.lowest.time);
  const lowestLabel = CATEGORY_LABELS[forecast.lowest.category];
  const firstAqi = forecast.hours[0]?.aqi ?? forecast.lowest.aqi;
  const lastAqi = forecast.hours[forecast.hours.length - 1]?.aqi ?? forecast.lowest.aqi;
  const trendWord =
    lastAqi < firstAqi - 15
      ? "easing later in the window"
      : lastAqi > firstAqi + 15
        ? "rising over the next 12 hours"
        : "staying fairly steady over the next 12 hours";

  return (
    <section aria-labelledby="forecast-heading" className="purvai-card space-y-4 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 id="forecast-heading" className="text-xl font-semibold">
              12-hour forecast
            </h2>
            <span className="rounded-full border border-border bg-subtle px-2.5 py-0.5 text-xs font-medium text-text-2">
              {forecast.source_label}
            </span>
          </div>
          <p className="text-sm text-text-2">
            Lowest at <span className="tabular-data font-medium text-text">{lowestTime}</span> (
            <span className="tabular-data font-medium text-text">{forecast.lowest.aqi}</span>,{" "}
            {lowestLabel}). Air is {trendWord}.
          </p>
        </div>

        <button
          type="button"
          aria-pressed={showTable}
          onClick={() => setShowTable((prev) => !prev)}
          className="purvai-btn purvai-btn-secondary"
        >
          {showTable ? "Show as chart" : "Show as table"}
        </button>
      </div>

      {!showTable ? (
        <div className="h-[260px] w-full" aria-label="12-hour AQI forecast chart">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 10, right: 12, left: 0, bottom: 4 }}>
              {BANDS.map((band) => (
                <ReferenceArea
                  key={band.y1}
                  y1={band.y1}
                  y2={band.y2}
                  fill={band.fill}
                  fillOpacity="var(--aqi-band-opacity)"
                />
              ))}
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="timeIst"
                stroke="var(--text-2)"
                tick={{ fontSize: 12, fill: "var(--text-2)" }}
              />
              <YAxis
                domain={[0, 500]}
                stroke="var(--text-2)"
                tick={{ fontSize: 12, fill: "var(--text-2)" }}
                width={42}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "var(--surface)",
                  borderColor: "var(--border)",
                  borderRadius: "6px",
                  color: "var(--text)",
                }}
              />
              <Line
                type="monotone"
                dataKey="aqi"
                name="AQI"
                stroke="var(--primary)"
                strokeWidth={2.5}
                dot={{ r: 3, fill: "var(--primary)" }}
                activeDot={{ r: 5 }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-border text-xs font-medium text-muted">
                <th className="py-2 pr-4">Time (IST)</th>
                <th className="py-2 pr-4">AQI</th>
                <th className="py-2 pr-4">Category</th>
                <th className="py-2">Dominant</th>
              </tr>
            </thead>
            <tbody>
              {chartData.map((row) => (
                <tr key={row.timeIst} className="border-b border-border last:border-b-0">
                  <td className="tabular-data py-2 pr-4">{row.timeIst}</td>
                  <td className="tabular-data py-2 pr-4 font-medium">
                    {row.isFloor ? `${row.aqi}+` : row.aqi}
                  </td>
                  <td className="py-2 pr-4">{row.category}</td>
                  <td className="py-2">{row.dominant}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
