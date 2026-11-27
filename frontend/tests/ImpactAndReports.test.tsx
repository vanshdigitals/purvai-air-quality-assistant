import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import ImpactPage from "../src/features/impact/ImpactPage";
import ReportsPage from "../src/features/reports/ReportsPage";

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("ImpactPage and ReportsPage", () => {
  it("logs a trip, toggles table view, and deletes an activity", async () => {
    const user = userEvent.setup();
    const activities = [
      {
        id: 1,
        kind: "commute",
        mode: "metro",
        replaced_mode: "car_petrol",
        distance_km: 10,
        hours: null,
        co2_saved_g: 1380,
        occurred_at: "2026-11-27T10:00:00Z",
      },
    ];

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/impact/summary")) {
          return new Response(
            JSON.stringify({
              trips: activities.length,
              co2_saved_g: 1380,
              co2_saved_kg: 1.38,
              distance_km: 10,
              days: 7,
            }),
            { status: 200 }
          );
        }
        if (url.includes("/activities/1") && init?.method === "DELETE") {
          activities.length = 0;
          return new Response(null, { status: 204 });
        }
        if (url.includes("/activities") && init?.method === "POST") {
          return new Response(JSON.stringify(activities[0]), { status: 201 });
        }
        if (url.includes("/activities")) {
          return new Response(JSON.stringify(activities), { status: 200 });
        }
        return new Response("{}", { status: 200 });
      })
    );

    renderWithClient(<ImpactPage />);

    expect(await screen.findByText("1.38 kg")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Table view" }));
    expect(await screen.findByText("1380 g")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Delete" }));
    await user.click(screen.getByRole("button", { name: "Confirm delete" }));
    expect(await screen.findByText(/No trips logged/i)).toBeInTheDocument();
  });

  it("shows demo banner when mode is demo and runs clear-data confirmation", async () => {
    const user = userEvent.setup();

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/health")) {
          return new Response(
            JSON.stringify({
              status: "ok",
              app: "purvai",
              version: "0.1.0",
              mode: "demo",
              database: { status: "ok", storage: "temporary", schema_revision: "0003" },
              time: "2026-11-27T10:00:00Z",
            }),
            { status: 200 }
          );
        }
        if (url.includes("/data") && init?.method === "DELETE") {
          return new Response(JSON.stringify({ deleted: true }), { status: 200 });
        }
        return new Response("[]", { status: 200 });
      })
    );

    renderWithClient(<ReportsPage />);

    expect(await screen.findByText(/Demo mode uses temporary storage/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Delete all household data" }));
    await user.click(screen.getByRole("button", { name: "Confirm delete all data" }));
    expect(await screen.findByText(/All household data deleted/i)).toBeInTheDocument();
  });
});
