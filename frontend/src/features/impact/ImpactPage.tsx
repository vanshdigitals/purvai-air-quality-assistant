import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import {
  type ActivityItem,
  deleteActivity,
  fetchActivities,
  fetchImpactSummary,
  postActivity,
} from "../../lib/api";

const TRAVEL_MODES = [
  { value: "metro", label: "Metro" },
  { value: "bus_diesel", label: "Bus (Diesel)" },
  { value: "bus_cng", label: "Bus (CNG)" },
  { value: "cycle", label: "Cycle" },
  { value: "walk", label: "Walk" },
  { value: "auto_cng", label: "Auto (CNG)" },
  { value: "scooter", label: "Scooter" },
  { value: "car_petrol", label: "Car (Petrol)" },
];

export default function ImpactPage() {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState("metro");
  const [replacedMode, setReplacedMode] = useState("car_petrol");
  const [distanceKm, setDistanceKm] = useState("10");
  const [viewMode, setViewMode] = useState<"chart" | "table">("chart");
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const summaryQuery = useQuery({
    queryKey: ["impact-summary", 7],
    queryFn: () => fetchImpactSummary(7),
  });

  const activitiesQuery = useQuery({
    queryKey: ["activities", 7],
    queryFn: () => fetchActivities(7),
  });

  const createMutation = useMutation({
    mutationFn: () => {
      const km = Number.parseFloat(distanceKm);
      return postActivity({
        kind: "commute",
        mode,
        replaced_mode: replacedMode,
        distance_km: Number.isFinite(km) ? km : 0,
      });
    },
    onSuccess: () => {
      setErrorMsg(null);
      void queryClient.invalidateQueries({ queryKey: ["activities"] });
      void queryClient.invalidateQueries({ queryKey: ["impact-summary"] });
    },
    onError: (err: Error) => {
      setErrorMsg(err.message);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteActivity(id),
    onSuccess: () => {
      setConfirmDeleteId(null);
      void queryClient.invalidateQueries({ queryKey: ["activities"] });
      void queryClient.invalidateQueries({ queryKey: ["impact-summary"] });
    },
  });

  const activities: ActivityItem[] = activitiesQuery.data ?? [];
  const summary = summaryQuery.data;

  const chartData = activities.map((act) => ({
    label: `${act.mode ?? act.kind} (${act.occurred_at.slice(5, 10)})`,
    co2SavedG: Math.round(act.co2_saved_g ?? 0),
  }));

  return (
    <section className="max-w-[780px] space-y-6">
      <header className="space-y-1">
        <h1>Impact &amp; CO₂ Savings</h1>
        <p className="text-text-2">
          Track commute shifts and estimate lifecycle CO₂e avoided using ITF-2023 India factors.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="rounded-lg border border-border bg-surface p-4">
          <div className="text-sm text-text-2">Trips (7 days)</div>
          <div className="mt-1 text-2xl font-semibold">{summary ? summary.trips : "—"}</div>
        </div>
        <div className="rounded-lg border border-border bg-surface p-4">
          <div className="text-sm text-text-2">CO₂ avoided</div>
          <div className="mt-1 text-2xl font-semibold">
            {summary ? `${summary.co2_saved_kg.toFixed(2)} kg` : "—"}
          </div>
        </div>
        <div className="rounded-lg border border-border bg-surface p-4">
          <div className="text-sm text-text-2">Distance shifted</div>
          <div className="mt-1 text-2xl font-semibold">
            {summary ? `${summary.distance_km.toFixed(1)} km` : "—"}
          </div>
        </div>
      </div>

      <form
        className="rounded-lg border border-border bg-surface p-4 space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          createMutation.mutate();
        }}
      >
        <h2 className="text-base font-semibold">Log a trip</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <label className="flex flex-col gap-1 text-sm">
            <span>Mode taken</span>
            <select
              aria-label="Mode taken"
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              className="rounded border border-border bg-bg px-3 py-2"
            >
              {TRAVEL_MODES.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1 text-sm">
            <span>Replaced mode</span>
            <select
              aria-label="Replaced mode"
              value={replacedMode}
              onChange={(e) => setReplacedMode(e.target.value)}
              className="rounded border border-border bg-bg px-3 py-2"
            >
              {TRAVEL_MODES.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1 text-sm">
            <span>Distance (km)</span>
            <input
              aria-label="Distance (km)"
              type="number"
              min="0.1"
              max="500"
              step="0.1"
              value={distanceKm}
              onChange={(e) => setDistanceKm(e.target.value)}
              className="rounded border border-border bg-bg px-3 py-2"
            />
          </label>
        </div>

        {errorMsg ? (
          <p role="alert" className="text-sm text-red-600">
            {errorMsg}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={createMutation.isPending}
          className="rounded bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {createMutation.isPending ? "Saving..." : "Log trip"}
        </button>
      </form>

      <div className="rounded-lg border border-border bg-surface p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">Recent activity</h2>
          <div className="flex gap-2" role="group" aria-label="View mode">
            <button
              type="button"
              onClick={() => setViewMode("chart")}
              aria-pressed={viewMode === "chart"}
              className="rounded border border-border px-3 py-1 text-sm"
            >
              Chart view
            </button>
            <button
              type="button"
              onClick={() => setViewMode("table")}
              aria-pressed={viewMode === "table"}
              className="rounded border border-border px-3 py-1 text-sm"
            >
              Table view
            </button>
          </div>
        </div>

        {activities.length === 0 ? (
          <p className="text-sm text-text-2">No trips logged in the last 7 days.</p>
        ) : viewMode === "chart" ? (
          <div className="h-56 w-full" aria-label="CO2 saved bar chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <XAxis dataKey="label" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="co2SavedG" fill="#2e7d32" name="CO₂ avoided (g)" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border text-text-2">
                  <th className="py-2">Date</th>
                  <th className="py-2">Mode</th>
                  <th className="py-2">Replaced</th>
                  <th className="py-2">Distance</th>
                  <th className="py-2">CO₂ avoided</th>
                  <th className="py-2">Action</th>
                </tr>
              </thead>
              <tbody>
                {activities.map((act) => (
                  <tr key={act.id} className="border-b border-border">
                    <td className="py-2">{act.occurred_at.slice(0, 10)}</td>
                    <td className="py-2">{act.mode ?? act.kind}</td>
                    <td className="py-2">{act.replaced_mode ?? "—"}</td>
                    <td className="py-2">
                      {act.distance_km !== null ? `${act.distance_km} km` : "—"}
                    </td>
                    <td className="py-2">
                      {act.co2_saved_g !== null ? `${Math.round(act.co2_saved_g)} g` : "—"}
                    </td>
                    <td className="py-2">
                      {confirmDeleteId === act.id ? (
                        <span className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => deleteMutation.mutate(act.id)}
                            className="text-red-600 underline"
                          >
                            Confirm delete
                          </button>
                          <button
                            type="button"
                            onClick={() => setConfirmDeleteId(null)}
                            className="text-text-2 underline"
                          >
                            Cancel
                          </button>
                        </span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setConfirmDeleteId(act.id)}
                          className="text-text-2 underline"
                        >
                          Delete
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
