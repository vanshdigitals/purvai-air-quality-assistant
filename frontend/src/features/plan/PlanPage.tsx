import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertCircle, ChevronDown, RefreshCw, ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Link } from "react-router";

import { AqiCategoryChip } from "../../components/AqiCategoryChip";
import { ApiError, buildPlan, fetchHousehold } from "../../lib/api";
import { formatIstTimeWithZone } from "../../lib/datetime";

type PlanDay = "today" | "tomorrow";

const PERIOD_TITLES: Record<string, string> = {
  morning: "Morning",
  afternoon: "Afternoon",
  evening: "Evening",
  night: "Night",
};

export default function PlanPage() {
  const [day, setDay] = useState<PlanDay>("today");
  const dayRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const householdQuery = useQuery({
    queryKey: ["household"],
    queryFn: fetchHousehold,
    retry: false,
  });

  const planMutation = useMutation({
    mutationFn: (targetDay: PlanDay) => buildPlan(targetDay),
  });

  useEffect(() => {
    if (householdQuery.data) {
      planMutation.mutate(day);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [day, householdQuery.data?.id]);

  const handleDayKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (
      event.key === "ArrowRight" ||
      event.key === "ArrowLeft" ||
      event.key === "Home" ||
      event.key === "End"
    ) {
      event.preventDefault();
      const nextIndex = event.key === "Home" ? 0 : event.key === "End" ? 1 : index === 0 ? 1 : 0;
      const nextDay: PlanDay = nextIndex === 0 ? "today" : "tomorrow";
      setDay(nextDay);
      dayRefs.current[nextIndex]?.focus();
    }
  };

  const plan = planMutation.data;
  const errorMessage =
    planMutation.error instanceof ApiError
      ? planMutation.error.message
      : "Could not build protection plan.";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="space-y-1">
          <h1>Daily Protection Plan</h1>
          <p className="text-text-2">
            Four time windows tailored from forecast and station air readings.
          </p>
        </div>

        <Link to="/today" className="purvai-btn purvai-btn-ghost">
          Back to Today
        </Link>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div
          role="radiogroup"
          aria-label="Plan day"
          className="inline-flex gap-1 rounded-[10px] border border-border bg-subtle p-1"
        >
          {(["today", "tomorrow"] as const).map((option, idx) => {
            const selected = day === option;
            return (
              <button
                key={option}
                ref={(el) => {
                  dayRefs.current[idx] = el;
                }}
                type="button"
                role="radio"
                aria-checked={selected}
                tabIndex={selected ? 0 : -1}
                onClick={() => setDay(option)}
                onKeyDown={(e) => handleDayKeyDown(e, idx)}
                className="purvai-segment"
              >
                {option === "today" ? "Today" : "Tomorrow"}
              </button>
            );
          })}
        </div>

        <button
          type="button"
          disabled={planMutation.isPending}
          onClick={() => planMutation.mutate(day)}
          className="purvai-btn purvai-btn-tertiary"
        >
          <RefreshCw size={18} aria-hidden />
          <span>Rebuild</span>
        </button>
      </div>

      {day === "tomorrow" && (
        <p className="text-sm text-text-2">
          <span className="rounded-full border border-border bg-subtle px-2.5 py-0.5 text-xs font-medium text-text-2">
            Modelled
          </span>{" "}
          Tomorrow&apos;s plan uses Open-Meteo CAMS hourly forecast data.
        </p>
      )}

      {planMutation.isPending && !plan && (
        <div aria-busy="true" className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {[0, 1, 2, 3].map((slot) => (
            <div key={slot} className="purvai-card h-[160px] animate-pulse bg-subtle p-5" />
          ))}
        </div>
      )}

      {planMutation.isError && (
        <div
          role="alert"
          className="purvai-card flex items-start gap-2 border-danger bg-danger-tint p-5 text-sm text-danger"
        >
          <AlertCircle size={18} className="mt-0.5 shrink-0" aria-hidden />
          <span>{errorMessage}</span>
        </div>
      )}

      {plan && (
        <>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {plan.periods.map((period) => {
              const title = PERIOD_TITLES[period.period] ?? period.period;
              if (period.past) {
                return (
                  <details
                    key={period.period}
                    className="purvai-card border-border bg-subtle p-5 text-text-2"
                  >
                    <summary className="flex min-h-[44px] cursor-pointer list-none items-center justify-between">
                      <div>
                        <span className="font-heading text-base font-medium text-text-2">
                          {title}
                        </span>{" "}
                        <span className="tabular-data text-xs text-muted">
                          {period.start}–{period.end}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 text-xs text-muted">
                        <span>Earlier today</span>
                        <ChevronDown size={16} aria-hidden />
                      </div>
                    </summary>
                    <p className="mt-3 text-xs text-muted">
                      Peak AQI in this window was <span className="tabular-data">{period.aqi}</span>
                      .
                    </p>
                  </details>
                );
              }

              return (
                <section
                  key={period.period}
                  aria-label={`${title} plan`}
                  className="purvai-card space-y-4 p-5"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <h2 className="text-lg font-semibold">{title}</h2>
                      <p className="tabular-data text-xs text-muted">
                        {period.start}–{period.end} IST · Peak AQI {period.aqi}
                      </p>
                    </div>
                    <AqiCategoryChip category={period.level} />
                  </div>

                  <ul className="space-y-2.5">
                    {period.items.map((item) => (
                      <li
                        key={item.action_id}
                        className="flex items-start justify-between gap-3 rounded-[6px] border border-border bg-subtle px-3 py-2.5 text-sm"
                      >
                        <span className="flex items-start gap-2">
                          <ShieldCheck
                            size={16}
                            className="mt-0.5 shrink-0 text-accent"
                            aria-hidden
                          />
                          <span>{item.text}</span>
                        </span>
                        <span className="shrink-0 rounded-full border border-border bg-surface px-2 py-0.5 text-xs text-text-2">
                          Rule
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              );
            })}
          </div>

          <p className="text-xs text-muted">
            Built {formatIstTimeWithZone(plan.generated_at)} from CPCB and CAMS data
          </p>
        </>
      )}
    </div>
  );
}
