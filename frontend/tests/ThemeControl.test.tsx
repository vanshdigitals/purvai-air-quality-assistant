import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import SettingsPage from "../src/features/settings/SettingsPage";
import { THEME_STORAGE_KEY } from "../src/lib/theme";

describe("SettingsPage ThemeControl", () => {
  it("switches data-theme, persists to localStorage, and saves via PUT /household", async () => {
    const user = userEvent.setup();
    const putBodies: string[] = [];

    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.endsWith("/household") && init?.method === "PUT") {
        putBodies.push(String(init.body ?? ""));
        return Promise.resolve(
          new Response(String(init.body), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          })
        );
      }
      return Promise.resolve(
        new Response(
          JSON.stringify({
            id: "hh-1",
            mode: "local",
            updated_at: "2026-11-27T10:00:00Z",
            members: [{ kind: "adult", count: 1 }],
            location: { label: "Sector 62, Noida", lat: 28.6271, lon: 77.3716 },
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

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <SettingsPage />
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(await screen.findByText("Sector 62, Noida")).toBeInTheDocument();

    const darkRadio = screen.getByRole("radio", { name: "Dark" });
    await user.click(darkRadio);

    expect(darkRadio).toHaveAttribute("aria-checked", "true");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(putBodies.length).toBeGreaterThanOrEqual(1);
    expect(putBodies[0]).toContain('"theme":"dark"');

    // ArrowLeft from Dark moves to Light
    await user.keyboard("{ArrowLeft}");
    const lightRadio = screen.getByRole("radio", { name: "Light" });
    expect(lightRadio).toHaveAttribute("aria-checked", "true");
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
  });
});
