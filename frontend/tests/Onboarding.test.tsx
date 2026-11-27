import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";

import HouseholdStepPage from "../src/features/onboarding/HouseholdStepPage";
import LocationStepPage from "../src/features/onboarding/LocationStepPage";
import { OnboardingLayout } from "../src/features/onboarding/OnboardingLayout";

describe("Onboarding flow", () => {
  it("supports location search, manual fallback on error, and skip after location", async () => {
    const user = userEvent.setup();
    let searchFail = true;
    const savedBodies: string[] = [];

    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/locations/search")) {
        if (searchFail) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                error: {
                  code: "PROVIDER_UNAVAILABLE",
                  message: "Location search is temporarily unavailable.",
                },
              }),
              { status: 502, headers: { "Content-Type": "application/json" } }
            )
          );
        }
        return Promise.resolve(
          new Response(
            JSON.stringify([
              {
                label: "Sector 62, Noida",
                lat: 28.6271,
                lon: 77.3716,
                city: "Noida",
                admin1: "Uttar Pradesh",
                admin2: "Noida",
                nearest_station_km: 1.3,
              },
            ]),
            { status: 200, headers: { "Content-Type": "application/json" } }
          )
        );
      }
      if (url.endsWith("/household") && init?.method === "PUT") {
        savedBodies.push(String(init.body ?? ""));
        return Promise.resolve(
          new Response(String(init.body), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          })
        );
      }
      return Promise.resolve(
        new Response(JSON.stringify({ mode: "local" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      );
    });

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/welcome/location"]}>
          <Routes>
            <Route path="/welcome" element={<OnboardingLayout />}>
              <Route path="location" element={<LocationStepPage />} />
              <Route path="household" element={<HouseholdStepPage />} />
            </Route>
            <Route path="/today" element={<h1>Today Landed</h1>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    const searchInput = screen.getByLabelText("Search city or neighbourhood");
    await user.type(searchInput, "Noida");

    // 502 error displays manual coordinate entry automatically
    expect(
      await screen.findByText("Location search is unavailable. Enter coordinates manually below.")
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Latitude")).toBeInTheDocument();

    // Retry search with working API
    searchFail = false;
    await user.clear(searchInput);
    await user.type(searchInput, "Noida");

    const resultOption = await screen.findByRole("radio", { name: /Sector 62, Noida/i });
    await user.click(resultOption);

    const skipBtn = screen.getByRole("button", { name: "Skip for now" });
    await user.click(skipBtn);

    expect(
      await screen.findByRole("heading", { level: 1, name: "Today Landed" })
    ).toBeInTheDocument();
    expect(savedBodies[0]).toContain('"kind":"adult","count":1');
  });

  it("toggles household checkbox cards cleanly", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ mode: "local" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/welcome/household?from=settings"]}>
          <Routes>
            <Route path="/welcome" element={<OnboardingLayout />}>
              <Route path="household" element={<HouseholdStepPage />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    const childCheckbox = screen.getByLabelText(/Child under 12/i);
    expect(childCheckbox).not.toBeChecked();
    await user.click(childCheckbox);
    expect(childCheckbox).toBeChecked();
  });
});
