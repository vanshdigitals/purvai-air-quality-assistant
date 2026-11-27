import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import TodayPage from "../src/features/today/TodayPage";

const HOUSEHOLD_MOCK = {
  id: "hh-1",
  mode: "local",
  updated_at: "2026-11-27T10:00:00Z",
  members: [
    { kind: "adult", count: 1 },
    { kind: "child_u12", count: 1 },
  ],
  location: { label: "Sector 62, Noida", lat: 28.6271, lon: 77.3716, city: "Noida" },
  settings: {
    theme: "system",
    commute_mode: "metro",
    ai_enabled: true,
    save_chat: false,
    reduce_motion: false,
  },
};

const AIR_BASE = {
  aqi: 312,
  aqi_is_floor: false,
  category: "very_poor",
  scale: "CPCB_NAQI",
  source_label: "Measured",
  source: { provider: "CPCB", station: "Sector-62, Noida", distance_km: 3.1 },
  observed_at: "2026-11-25T03:30:00Z",
  age_minutes: 40,
  stale: false,
  indicative: true,
  served_from_cache: false,
  dominant_pollutant: "pm25",
  pollutants: { pm25: { value: 135, unit: "µg/m³", sub_index: 312 } },
  verdict: {
    level: "very_poor",
    household_level: "severe",
    headline: "Stay indoors today. Run the purifier.",
    action_ids: ["stay_indoors", "purifier_on", "n95_if_out"],
    actions: [
      { action_id: "stay_indoors", text: "Stay indoors today.", tag: "rule" },
      { action_id: "purifier_on", text: "Run the purifier.", tag: "rule" },
      {
        action_id: "n95_if_out",
        text: "Wear a well-fitted N95 if you go out.",
        tag: "rule",
      },
    ],
  },
  grap: { stage: "II", order_date: "2026-11-02", source_url: "https://caqm.nic.in/" },
  attribution: ["CPCB", "data.gov.in"],
};

const FORECAST_BASE = {
  scale: "CPCB_NAQI",
  source_label: "Modelled",
  indicative: true,
  attribution: ["Open-Meteo", "CAMS"],
  generated_at: "2026-11-27T04:00:00Z",
  hours: [
    {
      time: "2026-11-27T05:00:00Z",
      aqi: 310,
      aqi_is_floor: false,
      category: "very_poor",
      dominant_pollutant: "pm25",
    },
    {
      time: "2026-11-27T11:00:00Z",
      aqi: 236,
      aqi_is_floor: false,
      category: "poor",
      dominant_pollutant: "pm25",
    },
  ],
  lowest: { time: "2026-11-27T11:00:00Z", aqi: 236, category: "poor" },
};

function renderToday() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <TodayPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function mockTodayApis(airOverride: Record<string, unknown> = {}) {
  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.endsWith("/household")) {
      return Promise.resolve(
        new Response(JSON.stringify(HOUSEHOLD_MOCK), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      );
    }
    if (url.includes("/air/forecast")) {
      return Promise.resolve(
        new Response(JSON.stringify(FORECAST_BASE), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      );
    }
    return Promise.resolve(
      new Response(JSON.stringify({ ...AIR_BASE, ...airOverride }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
  });
}

describe("TodayPage", () => {
  afterEach(() => {
    vi.useRealTimers();
    Object.defineProperty(window.navigator, "onLine", {
      configurable: true,
      value: true,
    });
  });

  it("renders verdict card and three rule action cards", async () => {
    mockTodayApis();
    renderToday();

    expect(await screen.findByText("Stay indoors today. Run the purifier.")).toBeInTheDocument();
    expect(screen.getByText(/Your household includes a child/i)).toBeInTheDocument();
    expect(screen.getAllByText("Rule").length).toBeGreaterThanOrEqual(4);
  });

  it("renders 401+ floor AQI hero with accessible label", async () => {
    mockTodayApis({ aqi: 401, aqi_is_floor: true, category: "severe" });
    renderToday();

    expect(await screen.findByText("401+")).toBeInTheDocument();
    expect(screen.getByLabelText("401, Severe, CPCB scale, Measured")).toBeInTheDocument();
  });

  it("renders stale banner at exactly 2 h 1 min under a fixed clock", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date("2026-11-27T05:31:00Z"));
    mockTodayApis({
      observed_at: "2026-11-27T03:30:00Z",
      age_minutes: 121,
      stale: true,
    });

    renderToday();
    expect(
      await screen.findByText("Data is 2 hours old. Showing the last reading.")
    ).toBeInTheDocument();
  });

  it("shows GRAP when present and hides GRAP when null", async () => {
    mockTodayApis();
    const { unmount } = renderToday();
    expect(await screen.findByText(/GRAP Stage II is in force for Delhi NCR/)).toBeInTheDocument();
    unmount();

    vi.restoreAllMocks();
    mockTodayApis({ grap: null });
    renderToday();
    expect(await screen.findByText("Stay indoors today. Run the purifier.")).toBeInTheDocument();
    expect(screen.queryByText(/GRAP Stage/)).not.toBeInTheDocument();
  });

  it("shows offline banner when offline with cached data", async () => {
    Object.defineProperty(window.navigator, "onLine", {
      configurable: true,
      value: false,
    });
    mockTodayApis({ observed_at: "2026-11-27T11:00:00Z" });

    renderToday();
    expect(await screen.findByText("Offline, showing data from 16:30 IST")).toBeInTheDocument();
  });

  it("toggles 12-hour forecast table and renders 11:00Z as 16:30 IST", async () => {
    const user = userEvent.setup();
    mockTodayApis();
    renderToday();

    const toggleBtn = await screen.findByRole(
      "button",
      { name: "Show as table" },
      { timeout: 4000 }
    );
    await user.click(toggleBtn);
    const table = screen.getByRole("table");
    expect(table).toBeInTheDocument();
    expect(within(table).getByText("16:30")).toBeInTheDocument();
  });

  it("shows error alert with Retry button when /air fails and recovers on retry", async () => {
    const user = userEvent.setup();
    let airAttempts = 0;

    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.endsWith("/household")) {
        return Promise.resolve(
          new Response(JSON.stringify(HOUSEHOLD_MOCK), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          })
        );
      }
      if (url.includes("/air/forecast")) {
        return Promise.resolve(
          new Response(JSON.stringify(FORECAST_BASE), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          })
        );
      }
      airAttempts += 1;
      if (airAttempts === 1) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              error: {
                code: "PROVIDER_UNAVAILABLE",
                message: "Air quality data is temporarily unavailable.",
                request_id: "r-1",
              },
            }),
            { status: 502, headers: { "Content-Type": "application/json" } }
          )
        );
      }
      return Promise.resolve(
        new Response(JSON.stringify(AIR_BASE), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      );
    });

    renderToday();
    expect(
      await screen.findByText("Air quality data is temporarily unavailable.")
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Stay indoors today. Run the purifier.")).toBeInTheDocument();
  });
});
