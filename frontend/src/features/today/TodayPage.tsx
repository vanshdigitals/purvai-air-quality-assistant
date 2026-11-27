import { useQuery } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, RefreshCw } from "lucide-react";

import { ApiError, fetchHealth } from "../../lib/api";

export default function TodayPage() {
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
  });

  const errorMessage =
    error instanceof ApiError
      ? error.message
      : error instanceof Error
        ? error.message
        : "Unable to reach the Purvai API.";

  return (
    <div className="space-y-6">
      <section className="space-y-2">
        <h1>Today</h1>
        <p className="max-w-[720px] text-text-2">Your daily verdict arrives in Phase 3.</p>
      </section>

      <section aria-labelledby="system-status-heading" className="purvai-card max-w-[720px] p-6">
        <div className="flex items-center justify-between gap-4">
          <h2 id="system-status-heading" className="text-lg font-semibold">
            System status
          </h2>
          {data && (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-success-tint px-3 py-1 text-xs font-medium text-success">
              <CheckCircle2 size={14} aria-hidden />
              <span>API connected</span>
            </span>
          )}
        </div>

        {isLoading && (
          <div aria-busy="true" aria-label="Loading system status" className="mt-4 space-y-3">
            <div className="h-4 w-48 animate-pulse rounded bg-subtle" />
            <div className="h-4 w-64 animate-pulse rounded bg-subtle" />
            <div className="h-4 w-40 animate-pulse rounded bg-subtle" />
          </div>
        )}

        {isError && (
          <div
            role="alert"
            className="mt-4 space-y-4 rounded-[6px] border border-danger bg-danger-tint p-4 text-danger"
          >
            <div className="flex items-start gap-2">
              <AlertCircle size={18} className="mt-0.5 shrink-0" aria-hidden />
              <p className="text-sm">{errorMessage}</p>
            </div>
            <button
              type="button"
              onClick={() => {
                void refetch();
              }}
              disabled={isFetching}
              className="purvai-btn purvai-btn-primary"
            >
              <RefreshCw size={18} aria-hidden />
              <span>Retry</span>
            </button>
          </div>
        )}

        {data && (
          <dl className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-[6px] border border-border bg-subtle px-4 py-3">
              <dt className="text-xs font-medium text-muted">Mode</dt>
              <dd className="tabular-data mt-1 text-sm font-medium text-text">{data.mode}</dd>
            </div>
            <div className="rounded-[6px] border border-border bg-subtle px-4 py-3">
              <dt className="text-xs font-medium text-muted">Database storage</dt>
              <dd className="tabular-data mt-1 text-sm font-medium text-text">
                {data.database.storage}
              </dd>
            </div>
            <div className="rounded-[6px] border border-border bg-subtle px-4 py-3">
              <dt className="text-xs font-medium text-muted">Schema revision</dt>
              <dd className="tabular-data mt-1 text-sm font-medium text-text">
                {data.database.schema_revision ?? "uninitialized"}
              </dd>
            </div>
          </dl>
        )}
      </section>
    </div>
  );
}
