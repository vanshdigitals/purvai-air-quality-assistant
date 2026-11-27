import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { AppShell } from "../src/components/AppShell";

function renderShell(mode: "local" | "demo" = "local", initialEntry = "/today") {
  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.endsWith("/health")) {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            status: "ok",
            app: "purvai",
            version: "0.1.0",
            mode,
            database: {
              status: "ok",
              storage: mode === "local" ? "persistent" : "temporary",
              schema_revision: "0002_location_admin",
            },
            time: "2026-11-27T10:00:00Z",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      );
    }
    return Promise.resolve(
      new Response(
        JSON.stringify({
          id: "hh-1",
          mode,
          updated_at: "2026-11-27T10:00:00Z",
          members: [{ kind: "adult", count: 1 }],
          location: { label: "Noida", lat: 28.62, lon: 77.37, city: "Noida" },
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
  });

  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/" element={<AppShell />}>
            <Route path="today" element={<h1>Today</h1>} />
            <Route path="ask" element={<h1>Ask Purvai</h1>} />
            <Route path="home-air" element={<h1>Home Air</h1>} />
            <Route path="impact" element={<h1>Impact</h1>} />
            <Route path="reports" element={<h1>Reports &amp; Data</h1>} />
            <Route path="settings" element={<h1>Settings</h1>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("AppShell", () => {
  it("renders landmarks, skip link, primary nav items, and active aria-current", () => {
    renderShell("local", "/today");

    const skipLink = screen.getByRole("link", { name: "Skip to main content" });
    expect(skipLink).toHaveAttribute("href", "#main-content");
    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();

    const primaryNav = screen.getByRole("navigation", { name: "Primary" });
    for (const label of ["Today", "Ask", "Home Air", "Impact"]) {
      expect(within(primaryNav).getByRole("link", { name: label })).toBeInTheDocument();
    }

    expect(within(primaryNav).getByRole("link", { name: "Today" })).toHaveAttribute(
      "aria-current",
      "page"
    );
    expect(within(primaryNav).getByRole("link", { name: "Ask" })).not.toHaveAttribute(
      "aria-current"
    );
  });

  it("shows demo banner when mode is demo", async () => {
    renderShell("demo", "/today");
    expect(await screen.findByText("Demo data resets. Export to keep it.")).toBeInTheDocument();
  });

  it("opens the mobile profile menu to reach Reports & Data and Settings", async () => {
    const user = userEvent.setup();
    renderShell("local", "/today");

    const menuButton = screen.getByRole("button", { name: "Reports and settings menu" });
    await user.click(menuButton);

    const mobileMenu = screen.getByRole("navigation", { name: "Account and workspace" });
    await user.click(within(mobileMenu).getByRole("link", { name: "Reports & Data" }));
    expect(screen.getByRole("heading", { level: 1, name: "Reports & Data" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Reports and settings menu" }));
    const mobileMenuAgain = screen.getByRole("navigation", { name: "Account and workspace" });
    await user.click(within(mobileMenuAgain).getByRole("link", { name: "Settings" }));
    expect(screen.getByRole("heading", { level: 1, name: "Settings" })).toBeInTheDocument();
  });
});
