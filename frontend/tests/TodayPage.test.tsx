import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import TodayPage from "../src/features/today/TodayPage";

function renderToday() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <TodayPage />
    </QueryClientProvider>
  );
}

describe("TodayPage System status", () => {
  it("shows loading skeleton then API connected state", async () => {
    let resolveFetch!: (value: Response) => void;
    vi.spyOn(globalThis, "fetch").mockImplementation(
      () =>
        new Promise<Response>((resolve) => {
          resolveFetch = resolve;
        })
    );

    renderToday();
    expect(screen.getByLabelText("Loading system status")).toBeInTheDocument();

    resolveFetch(
      new Response(
        JSON.stringify({
          status: "ok",
          app: "purvai",
          version: "0.1.0",
          mode: "local",
          database: {
            status: "ok",
            storage: "persistent",
            schema_revision: "0001_initial_schema",
          },
          time: "2026-11-27T10:00:00Z",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      )
    );

    expect(await screen.findByText("API connected")).toBeInTheDocument();
    expect(screen.getByText("local")).toBeInTheDocument();
    expect(screen.getByText("persistent")).toBeInTheDocument();
    expect(screen.getByText("0001_initial_schema")).toBeInTheDocument();
  });

  it("shows error alert with Retry button when API fails and recovers on retry", async () => {
    const user = userEvent.setup();
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            error: {
              code: "SERVICE_UNAVAILABLE",
              message: "Database integrity check failed",
              request_id: "r-test1",
            },
          }),
          { status: 503, headers: { "Content-Type": "application/json" } }
        )
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            status: "ok",
            app: "purvai",
            version: "0.1.0",
            mode: "local",
            database: {
              status: "ok",
              storage: "persistent",
              schema_revision: "0001_initial_schema",
            },
            time: "2026-11-27T10:00:00Z",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      );

    renderToday();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Database integrity check failed");

    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("API connected")).toBeInTheDocument();
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });
});
