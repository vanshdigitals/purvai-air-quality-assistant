import { X } from "lucide-react";
import { useEffect, useRef, type RefObject } from "react";

import type { AqiCategory } from "../../lib/api";

interface WhatDoesThisMeanSheetProps {
  open: boolean;
  currentCategory: AqiCategory;
  onClose: () => void;
  returnFocusRef: RefObject<HTMLElement | null>;
}

const BAND_ROWS: readonly {
  id: AqiCategory;
  name: string;
  aqiRange: string;
  pm25: string;
  pm10: string;
}[] = [
  { id: "good", name: "Good", aqiRange: "0–50", pm25: "0–30", pm10: "0–50" },
  { id: "satisfactory", name: "Satisfactory", aqiRange: "51–100", pm25: "31–60", pm10: "51–100" },
  { id: "moderate", name: "Moderate", aqiRange: "101–200", pm25: "61–90", pm10: "101–250" },
  { id: "poor", name: "Poor", aqiRange: "201–300", pm25: "91–120", pm10: "251–350" },
  { id: "very_poor", name: "Very Poor", aqiRange: "301–400", pm25: "121–250", pm10: "351–430" },
  { id: "severe", name: "Severe", aqiRange: "401+", pm25: "250+", pm10: "430+" },
];

export function WhatDoesThisMeanSheet({
  open,
  currentCategory,
  onClose,
  returnFocusRef,
}: WhatDoesThisMeanSheetProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const returnTarget = returnFocusRef.current;
    closeButtonRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key === "Tab" && dialogRef.current) {
        const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (!first || !last) return;
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      returnTarget?.focus();
    };
  }, [open, onClose, returnFocusRef]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="aqi-guide-title"
        className="purvai-card max-h-[90vh] w-full max-w-[480px] space-y-4 overflow-y-auto bg-surface p-6"
      >
        <div className="flex items-start justify-between gap-4">
          <h2 id="aqi-guide-title" className="text-xl font-semibold">
            What does this mean?
          </h2>
          <button
            ref={closeButtonRef}
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="purvai-btn purvai-btn-ghost min-w-[44px] px-2"
          >
            <X size={18} aria-hidden />
          </button>
        </div>

        <table className="w-full border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-border text-xs font-medium text-muted">
              <th className="py-2 pr-3">Category</th>
              <th className="py-2 pr-3">AQI</th>
              <th className="py-2 pr-3">PM2.5</th>
              <th className="py-2">PM10</th>
            </tr>
          </thead>
          <tbody>
            {BAND_ROWS.map((row) => {
              const active = row.id === currentCategory;
              return (
                <tr
                  key={row.id}
                  className={`border-b border-border last:border-b-0 ${
                    active ? "bg-selected font-medium" : ""
                  }`}
                >
                  <td className="py-2 pr-3">{row.name}</td>
                  <td className="tabular-data py-2 pr-3">{row.aqiRange}</td>
                  <td className="tabular-data py-2 pr-3">{row.pm25}</td>
                  <td className="tabular-data py-2">{row.pm10}</td>
                </tr>
              );
            })}
          </tbody>
        </table>

        <div className="space-y-2 text-sm text-text-2">
          <p>
            <strong className="font-medium text-text">Measured:</strong> official CPCB monitoring
            station within 10 km, updated within 2 hours.
          </p>
          <p>
            <strong className="font-medium text-text">Modelled:</strong> Open-Meteo CAMS estimate
            when no fresh nearby CPCB station is available.
          </p>
          <p>
            <strong className="font-medium text-text">Estimated:</strong> fewer than 3 pollutants
            reported, with PM2.5 or PM10 present.
          </p>
        </div>

        <p className="rounded-[6px] border border-border bg-subtle p-3 text-sm text-text">
          Purvai gives general guidance, not medical advice. If you have symptoms, contact a doctor.
        </p>
      </div>
    </div>
  );
}
