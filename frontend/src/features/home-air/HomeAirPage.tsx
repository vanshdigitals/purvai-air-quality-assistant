import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Wind } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";

import {
  calcHomeAir,
  fetchHomeAirTips,
  fetchHousehold,
  type HomeAirCalcRequest,
} from "../../lib/api";

interface FieldErrors {
  length_m?: string;
  width_m?: string;
  height_m?: string;
  cadr_m3h?: string;
}

export default function HomeAirPage() {
  const [lengthStr, setLengthStr] = useState("3.5");
  const [widthStr, setWidthStr] = useState("3.0");
  const [heightStr, setHeightStr] = useState("2.8");
  const [cadrStr, setCadrStr] = useState("250");
  const [errors, setErrors] = useState<FieldErrors>({});

  const errorSummaryRef = useRef<HTMLDivElement>(null);

  const householdQuery = useQuery({
    queryKey: ["household"],
    queryFn: fetchHousehold,
    retry: false,
  });

  const loc = householdQuery.data?.location;

  const tipsQuery = useQuery({
    queryKey: ["home-air", "tips", loc?.lat, loc?.lon],
    queryFn: () => {
      if (!loc) throw new Error("Location missing");
      return fetchHomeAirTips(loc.lat, loc.lon);
    },
    enabled: Boolean(loc),
  });

  const calcMutation = useMutation({
    mutationFn: (payload: HomeAirCalcRequest) => calcHomeAir(payload),
  });

  const validateAndSubmit = (event: FormEvent) => {
    event.preventDefault();
    const nextErrors: FieldErrors = {};

    const length = Number(lengthStr);
    const width = Number(widthStr);
    const height = Number(heightStr);
    const cadr = Number(cadrStr);

    if (!Number.isFinite(length) || length < 0.5 || length > 50) {
      nextErrors.length_m = "Length must be between 0.5 and 50 m.";
    }
    if (!Number.isFinite(width) || width < 0.5 || width > 50) {
      nextErrors.width_m = "Width must be between 0.5 and 50 m.";
    }
    if (!Number.isFinite(height) || height < 1.5 || height > 10) {
      nextErrors.height_m = "Ceiling height must be between 1.5 and 10 m.";
    }
    if (!Number.isFinite(cadr) || cadr < 20 || cadr > 2000) {
      nextErrors.cadr_m3h = "CADR must be between 20 and 2000 m³/h.";
    }

    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      window.setTimeout(() => errorSummaryRef.current?.focus(), 0);
      return;
    }

    calcMutation.mutate({
      length_m: length,
      width_m: width,
      height_m: height,
      cadr_m3h: cadr,
    });
  };

  const errorList = Object.entries(errors).filter(
    (entry): entry is [string, string] => typeof entry[1] === "string"
  );

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1>Home Air</h1>
        <p className="max-w-[720px] text-text-2">
          Check how many air changes per hour (ACH) your purifier delivers for your room size.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <form
          onSubmit={validateAndSubmit}
          noValidate
          className="purvai-card space-y-5 p-6 lg:col-span-6"
        >
          <h2 className="text-xl font-semibold">Room &amp; purifier calculator</h2>

          {errorList.length > 0 && (
            <div
              ref={errorSummaryRef}
              tabIndex={-1}
              role="alert"
              className="rounded-[6px] border border-danger bg-danger-tint p-3 text-sm text-danger"
            >
              <p className="font-medium">Please fix the following inputs:</p>
              <ul className="mt-1 list-disc pl-5">
                {errorList.map(([field, msg]) => (
                  <li key={field}>{msg}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div>
              <label htmlFor="room-length" className="mb-1 block text-sm font-medium">
                Length
              </label>
              <div className="relative">
                <input
                  id="room-length"
                  type="number"
                  step="0.1"
                  value={lengthStr}
                  onChange={(e) => setLengthStr(e.target.value)}
                  aria-invalid={Boolean(errors.length_m)}
                  aria-describedby={errors.length_m ? "err-length" : undefined}
                  className={`purvai-input tabular-data pr-9 ${errors.length_m ? "purvai-input-error" : ""}`}
                />
                <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted">
                  m
                </span>
              </div>
              {errors.length_m && (
                <p id="err-length" className="mt-1 text-xs text-danger">
                  {errors.length_m}
                </p>
              )}
            </div>

            <div>
              <label htmlFor="room-width" className="mb-1 block text-sm font-medium">
                Width
              </label>
              <div className="relative">
                <input
                  id="room-width"
                  type="number"
                  step="0.1"
                  value={widthStr}
                  onChange={(e) => setWidthStr(e.target.value)}
                  aria-invalid={Boolean(errors.width_m)}
                  aria-describedby={errors.width_m ? "err-width" : undefined}
                  className={`purvai-input tabular-data pr-9 ${errors.width_m ? "purvai-input-error" : ""}`}
                />
                <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted">
                  m
                </span>
              </div>
              {errors.width_m && (
                <p id="err-width" className="mt-1 text-xs text-danger">
                  {errors.width_m}
                </p>
              )}
            </div>

            <div>
              <label htmlFor="room-height" className="mb-1 block text-sm font-medium">
                Height
              </label>
              <div className="relative">
                <input
                  id="room-height"
                  type="number"
                  step="0.1"
                  value={heightStr}
                  onChange={(e) => setHeightStr(e.target.value)}
                  aria-invalid={Boolean(errors.height_m)}
                  aria-describedby={errors.height_m ? "err-height" : undefined}
                  className={`purvai-input tabular-data pr-9 ${errors.height_m ? "purvai-input-error" : ""}`}
                />
                <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted">
                  m
                </span>
              </div>
              {errors.height_m && (
                <p id="err-height" className="mt-1 text-xs text-danger">
                  {errors.height_m}
                </p>
              )}
            </div>
          </div>

          <div>
            <label htmlFor="purifier-cadr" className="mb-1 block text-sm font-medium">
              Purifier CADR
            </label>
            <div className="relative">
              <input
                id="purifier-cadr"
                type="number"
                step="1"
                value={cadrStr}
                onChange={(e) => setCadrStr(e.target.value)}
                aria-invalid={Boolean(errors.cadr_m3h)}
                aria-describedby={errors.cadr_m3h ? "err-cadr cadr-help" : "cadr-help"}
                className={`purvai-input tabular-data pr-14 ${errors.cadr_m3h ? "purvai-input-error" : ""}`}
              />
              <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted">
                m³/h
              </span>
            </div>
            <p id="cadr-help" className="mt-1 text-xs text-muted">
              Find CADR on the box or spec sheet.
            </p>
            {errors.cadr_m3h && (
              <p id="err-cadr" className="mt-1 text-xs text-danger">
                {errors.cadr_m3h}
              </p>
            )}
          </div>

          <button
            type="submit"
            disabled={calcMutation.isPending}
            className="purvai-btn purvai-btn-primary"
          >
            Calculate ACH
          </button>
        </form>

        <div className="space-y-4 lg:col-span-6">
          {calcMutation.data && (
            <section aria-live="polite" className="purvai-card space-y-4 p-6">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="text-xs font-medium uppercase tracking-wide text-muted">
                    Air changes per hour
                  </div>
                  <div className="aqi-hero-number text-text">
                    {calcMutation.data.ach.toFixed(1)}
                  </div>
                  <div className="text-sm text-text-2">
                    ACH · Room volume{" "}
                    <span className="tabular-data font-medium text-text">
                      {calcMutation.data.volume_m3.toFixed(1)} m³
                    </span>
                  </div>
                </div>

                <span
                  className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-medium ${
                    calcMutation.data.meets_target
                      ? "bg-success-tint text-success"
                      : "bg-warning-tint text-warning"
                  }`}
                >
                  {calcMutation.data.meets_target ? (
                    <>
                      <CheckCircle2 size={16} aria-hidden />
                      <span>Meets target</span>
                    </>
                  ) : (
                    <>
                      <AlertTriangle size={16} aria-hidden />
                      <span>Below target</span>
                    </>
                  )}
                </span>
              </div>

              <p className="text-sm text-text-2">
                Target: 5 air changes per hour in smog season (Purvai design target). Required CADR
                for this room:{" "}
                <span className="tabular-data font-medium text-text">
                  {calcMutation.data.cadr_needed_m3h} m³/h
                </span>
                .
              </p>
            </section>
          )}

          {tipsQuery.data?.ventilation_hour && (
            <section className="purvai-card flex items-center justify-between gap-3 p-5">
              <div className="flex items-center gap-3">
                <Wind size={20} className="shrink-0 text-accent" aria-hidden />
                <div>
                  <div className="text-sm font-medium text-text">
                    Cleanest daytime ventilation window:{" "}
                    <span className="tabular-data">{tipsQuery.data.ventilation_hour}</span>
                  </div>
                  <div className="text-xs text-muted">Based on 12-hour forecast</div>
                </div>
              </div>
              <span className="rounded-full border border-border bg-subtle px-2.5 py-0.5 text-xs font-medium text-text-2">
                Modelled
              </span>
            </section>
          )}

          {tipsQuery.data && (
            <section aria-labelledby="home-tips-heading" className="purvai-card space-y-3 p-6">
              <h2 id="home-tips-heading" className="text-xl font-semibold">
                Indoor tips
              </h2>
              <ul className="space-y-2.5 text-sm">
                {tipsQuery.data.tips.map((tip) => (
                  <li
                    key={tip.tip_id}
                    className="rounded-[6px] border border-border bg-subtle px-3.5 py-2.5 text-text"
                  >
                    {tip.text}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
