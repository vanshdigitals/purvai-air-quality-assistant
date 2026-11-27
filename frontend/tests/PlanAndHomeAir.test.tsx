import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import HomeAirPage from "../src/features/home-air/HomeAirPage";
import PlanPage from "../src/features/plan/PlanPage";

describe("PlanPage and HomeAirPage", () => {
  it("renders 4 periods on PlanPage and switches between Today and Tomorrow", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.endsWith("/household")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: "hh-1",
              mode: "local",
              updated_at: "2026-11-27T10:00:00Z",
              members: [{ kind: "adult", count: 1 }],
              location: { label: "Noida", lat: 28.62, lon: 77.37 },
              settings: {
                theme: "system",
                commute_mode: "metro",
                ai_enabled: true,
                save_chat: false,
                reduce_motion: false,
              },
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          )
        );
      }
      const parsed = JSON.parse(String(init?.body ?? '{"day":"today"}')) as { day: string };
      return Promise.resolve(
        new Response(
          JSON.stringify({
            plan_date: parsed.day === "today" ? "2026-11-27" : "2026-11-28",
            day: parsed.day,
            generated_by: "rules",
            generated_at: "2026-11-27T04:00:00Z",
            source_label: parsed.day === "today" ? "Measured" : "Modelled",
            periods: [
              {
                period: "morning",
                start: "06:00",
                end: "12:00",
                level: "very_poor",
                aqi: 312,
                past: false,
                items: [
                  {
                    action_id: "no_outdoor_exercise",
                    text: "Avoid outdoor exercise.",
                    tag: "rule",
                  },
                ],
              },
              {
                period: "afternoon",
                start: "12:00",
                end: "17:00",
                level: "poor",
                aqi: 250,
                past: false,
                items: [
                  { action_id: "exercise_indoors", text: "Move exercise indoors.", tag: "rule" },
                ],
              },
              {
                period: "evening",
                start: "17:00",
                end: "21:00",
                level: "very_poor",
                aqi: 330,
                past: false,
                items: [
                  {
                    action_id: "n95_if_out",
                    text: "Wear a well-fitted N95 if you go out.",
                    tag: "rule",
                  },
                ],
              },
              {
                period: "night",
                start: "21:00",
                end: "06:00",
                level: "very_poor",
                aqi: 340,
                past: false,
                items: [
                  {
                    action_id: "no_outdoor_exercise",
                    text: "Avoid outdoor exercise.",
                    tag: "rule",
                  },
                ],
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      );
    });

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <PlanPage />
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(await screen.findByText("Morning")).toBeInTheDocument();
    expect(screen.getByText("Afternoon")).toBeInTheDocument();
    expect(screen.getByText("Evening")).toBeInTheDocument();
    expect(screen.getByText("Night")).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: "Tomorrow" }));
    expect(
      await screen.findByText(/Tomorrow's plan uses Open-Meteo CAMS hourly forecast data/)
    ).toBeInTheDocument();
  });

  it("validates HomeAirPage inputs and renders ACH calculation result", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.endsWith("/home-air/calc")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              volume_m3: 29.4,
              ach: 8.5,
              target_ach: 5,
              meets_target: true,
              cadr_needed_m3h: 147,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          )
        );
      }
      return Promise.resolve(
        new Response(JSON.stringify({ detail: "not mocked" }), { status: 404 })
      );
    });

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <HomeAirPage />
        </MemoryRouter>
      </QueryClientProvider>
    );

    const lengthInput = screen.getByLabelText("Length");
    await user.clear(lengthInput);
    await user.type(lengthInput, "0.1");
    await user.click(screen.getByRole("button", { name: "Calculate ACH" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Length must be between 0.5 and 50 m."
    );

    await user.clear(lengthInput);
    await user.type(lengthInput, "3.5");
    await user.click(screen.getByRole("button", { name: "Calculate ACH" }));
    expect(await screen.findByText("8.5")).toBeInTheDocument();
    expect(screen.getByText("Meets target")).toBeInTheDocument();
  });
});
