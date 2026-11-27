import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import AskPage from "../src/features/ask/AskPage";
import SettingsPage from "../src/features/settings/SettingsPage";

function makeHousehold(saveChat = false, aiEnabled = true) {
  return {
    id: "hh-1",
    mode: "local",
    updated_at: "2026-11-27T10:00:00Z",
    members: [{ kind: "adult", count: 1 }],
    location: { label: "Sector 62, Noida", lat: 28.6271, lon: 77.3716, city: "Noida" },
    settings: {
      theme: "system",
      commute_mode: "metro",
      ai_enabled: aiEnabled,
      save_chat: saveChat,
      reduce_motion: false,
    },
  };
}

function renderAsk() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AskPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("AskPage and Settings AI", () => {
  it("renders empty state, sends suggested chip, enforces 500-char limit, and shows chips + doctor note", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.endsWith("/household")) {
        return Promise.resolve(
          new Response(JSON.stringify(makeHousehold(false, true)), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          })
        );
      }
      if (url.endsWith("/chat")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              schema_version: "1.0",
              verdict_level: "severe",
              answer: "PM2.5 is high at 312 AQI. Stay indoors today.",
              data_cited: ["aqi", "category", "source", "grap"],
              recommendations: [
                {
                  action_id: "stay_indoors",
                  title: "Keep children indoors",
                  why: "Sensitive members face higher risk.",
                  tag: "ai_wording",
                },
              ],
              needs_doctor_note: true,
              out_of_scope: false,
              generated_by: "gemini",
              note: null,
              aqi: 312,
              category: "very_poor",
              source_label: "Modelled",
              observed_at: "2026-11-27T11:00:00Z",
              age_minutes: 30,
              stale: false,
              grap_stage: "II",
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          )
        );
      }
      return Promise.resolve(new Response("{}", { status: 404 }));
    });

    renderAsk();

    expect(await screen.findByText("Chat history is off. Nothing is saved.")).toBeInTheDocument();
    const chip = screen.getByRole("button", { name: "Can my child play outside at 5 pm?" });
    await user.click(chip);

    expect(
      await screen.findByText("PM2.5 is high at 312 AQI. Stay indoors today.")
    ).toBeInTheDocument();
    expect(screen.getByText("AQI 312")).toBeInTheDocument();
    expect(screen.getByText("Modelled estimate")).toBeInTheDocument();
    expect(screen.getByText("GRAP Stage II")).toBeInTheDocument();
    expect(screen.getByText("AI wording")).toBeInTheDocument();
    expect(screen.getByText("Worded by Gemini")).toBeInTheDocument();
    expect(screen.getByText(/Consult a doctor/)).toBeInTheDocument();

    // Test 500-char counter and disable over limit
    const textarea = screen.getByLabelText("Ask a question");
    await user.type(textarea, "hello");
    expect(screen.getByText("5/500")).toBeInTheDocument();

    // Paste 501 characters
    await user.clear(textarea);
    await user.click(textarea);
    await user.paste("x".repeat(501));
    expect(screen.getByText("501/500")).toBeInTheDocument();
    expect(screen.getByText("Questions must be 500 characters or fewer.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("shows template fallback banner and 429 Retry-After countdown message", async () => {
    const user = userEvent.setup();
    let callNum = 0;

    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.endsWith("/household")) {
        return Promise.resolve(
          new Response(JSON.stringify(makeHousehold(false, true)), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          })
        );
      }
      callNum += 1;
      if (callNum === 1) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              schema_version: "1.0",
              verdict_level: "severe",
              answer: "Stay indoors today. (AI unavailable, showing standard advice)",
              data_cited: ["aqi", "category", "source"],
              recommendations: [
                {
                  action_id: "stay_indoors",
                  title: "Stay indoors today.",
                  why: "Rule guidance.",
                  tag: "rule",
                },
              ],
              needs_doctor_note: false,
              out_of_scope: false,
              generated_by: "template",
              note: "AI unavailable, showing standard advice",
              aqi: 312,
              category: "very_poor",
              source_label: "Measured",
              observed_at: "2026-11-27T11:00:00Z",
              age_minutes: 30,
              stale: false,
              grap_stage: null,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          )
        );
      }
      return Promise.resolve(
        new Response(
          JSON.stringify({
            error: {
              code: "RATE_LIMIT_EXCEEDED",
              message: "Too many requests.",
              request_id: "r-429",
            },
          }),
          {
            status: 429,
            headers: { "Content-Type": "application/json", "Retry-After": "42" },
          }
        )
      );
    });

    renderAsk();
    await user.click(await screen.findByRole("button", { name: "Which mask should I use?" }));
    expect(await screen.findByText("AI unavailable, showing standard advice")).toBeInTheDocument();
    expect(screen.getByText("Standard advice")).toBeInTheDocument();

    const textarea = screen.getByLabelText("Ask a question");
    await user.type(textarea, "Next question");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(
      await screen.findByText("Too many questions. Try again in 42 seconds.")
    ).toBeInTheDocument();
  });

  it("loads saved history when save_chat is on and deletes it via confirmation dialog", async () => {
    const user = userEvent.setup();
    let deleteCalled = false;

    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.endsWith("/household")) {
        return Promise.resolve(
          new Response(JSON.stringify(makeHousehold(true, true)), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          })
        );
      }
      if (url.endsWith("/conversations") && init?.method === "DELETE") {
        deleteCalled = true;
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      if (url.endsWith("/conversations")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              messages: [
                {
                  id: 1,
                  role: "user",
                  text: "Saved question?",
                  generated_by: "user",
                  created_at: "2026-11-27T05:00:00Z",
                },
                {
                  id: 2,
                  role: "assistant",
                  text: "Saved answer.",
                  generated_by: "groq",
                  created_at: "2026-11-27T05:00:00Z",
                },
              ],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          )
        );
      }
      return Promise.resolve(new Response("{}", { status: 404 }));
    });

    renderAsk();

    expect(await screen.findByText("Saved question?")).toBeInTheDocument();
    expect(screen.getByText("Saved answer.")).toBeInTheDocument();
    expect(screen.getByText("Worded by Groq")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Delete chat history" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));

    expect(deleteCalled).toBe(true);
    expect(await screen.findByText("Ask about the air today")).toBeInTheDocument();
  });

  it("renders Settings AI toggles, disabled state when ai_available=false, and privacy notice", async () => {
    const user = userEvent.setup();
    const putBodies: string[] = [];
    let aiAvailable = false;

    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.endsWith("/health")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              status: "ok",
              app: "purvai",
              version: "0.1.0",
              mode: "local",
              ai_available: aiAvailable,
              database: { status: "ok", storage: "persistent", schema_revision: "0002" },
              time: "2026-11-27T10:00:00Z",
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          )
        );
      }
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
        new Response(JSON.stringify(makeHousehold(false, true)), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      );
    });

    const client1 = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { unmount } = render(
      <QueryClientProvider client={client1}>
        <MemoryRouter>
          <SettingsPage />
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(
      await screen.findByText("AI is not set up on this server. Standard advice is used.")
    ).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "AI personalisation" })).toBeDisabled();
    expect(
      screen.getByText(/Questions are sent to Google Gemini, or Groq as a backup/i)
    ).toBeInTheDocument();

    unmount();

    aiAvailable = true;
    const client2 = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client2}>
        <MemoryRouter>
          <SettingsPage />
        </MemoryRouter>
      </QueryClientProvider>
    );

    const saveChatSwitch = await screen.findByRole("switch", { name: "Save chat history" });
    await user.click(saveChatSwitch);
    expect(putBodies[0]).toContain('"save_chat":true');
  });
});
