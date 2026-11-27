import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Minus, Plus } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useOutletContext, useSearchParams } from "react-router";

import {
  fetchHealth,
  fetchHousehold,
  saveHousehold,
  type MemberInput,
  type MemberKind,
} from "../../lib/api";
import { OnboardingFrame, type OnboardingOutletContext } from "./OnboardingLayout";

interface SensitiveFlagOption {
  kind: Exclude<MemberKind, "adult">;
  label: string;
  description: string;
}

const FLAG_OPTIONS: readonly SensitiveFlagOption[] = [
  {
    kind: "child_u12",
    label: "Child under 12",
    description: "Escalates safety advice one category earlier.",
  },
  {
    kind: "adult_65p",
    label: "Adult over 65",
    description: "Earlier indoor precautions and symptom checks.",
  },
  {
    kind: "heart_lung",
    label: "Heart or lung condition",
    description: "Includes asthma, COPD, or cardiac sensitivity.",
  },
  {
    kind: "outdoor_worker",
    label: "Works outdoors",
    description: "Adds mask and indoor-break guidance from Poor AQI.",
  },
];

export default function HouseholdStepPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const fromSettings = searchParams.get("from") === "settings";
  const queryClient = useQueryClient();
  const { draft, setDraft } = useOutletContext<OnboardingOutletContext>();

  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
  });

  const existingHousehold = useQuery({
    queryKey: ["household"],
    queryFn: fetchHousehold,
    enabled: fromSettings,
    retry: false,
  });

  const headingRef = useRef<HTMLHeadingElement>(null);

  const initialMembers =
    fromSettings && existingHousehold.data ? existingHousehold.data.members : draft.members;

  const [adultCount, setAdultCount] = useState<number>(() => {
    const found = initialMembers.find((m) => m.kind === "adult")?.count;
    return found !== undefined ? found : 1;
  });
  const [flags, setFlags] = useState<Record<Exclude<MemberKind, "adult">, boolean>>(() => ({
    child_u12: initialMembers.some((m) => m.kind === "child_u12" && m.count > 0),
    adult_65p: initialMembers.some((m) => m.kind === "adult_65p" && m.count > 0),
    heart_lung: initialMembers.some((m) => m.kind === "heart_lung" && m.count > 0),
    outdoor_worker: initialMembers.some((m) => m.kind === "outdoor_worker" && m.count > 0),
  }));
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!fromSettings && !draft.location) {
      void navigate("/welcome/location", { replace: true });
    }
  }, [draft.location, fromSettings, navigate]);

  const saveMutation = useMutation({
    mutationFn: saveHousehold,
    onSuccess: (saved) => {
      queryClient.setQueryData(["household"], saved);
      void navigate("/settings", { replace: true });
    },
    onError: (err) => {
      setErrorMsg(err instanceof Error ? err.message : "Could not save household.");
    },
  });

  const buildMembers = (): MemberInput[] => {
    const list: MemberInput[] = [{ kind: "adult", count: adultCount }];
    for (const opt of FLAG_OPTIONS) {
      if (flags[opt.kind]) {
        list.push({ kind: opt.kind, count: 1 });
      }
    }
    return list;
  };

  const totalSelected = adultCount + Object.values(flags).filter((checked) => checked).length;

  const handleContinue = () => {
    if (totalSelected < 1) {
      setErrorMsg("Select at least one household member.");
      return;
    }
    const members = buildMembers();
    setDraft((prev) => ({ ...prev, members }));

    if (fromSettings && existingHousehold.data) {
      saveMutation.mutate({
        members,
        location: existingHousehold.data.location,
        settings: existingHousehold.data.settings,
      });
      return;
    }
    void navigate("/welcome/commute");
  };

  const privacyNote =
    healthQuery.data?.mode === "demo"
      ? "Demo data is deleted after 24 hours."
      : "This stays on your device.";

  return (
    <OnboardingFrame step={fromSettings ? 1 : 3} totalSteps={fromSettings ? 1 : 4}>
      <div className="space-y-6">
        <div className="space-y-2">
          <h1 ref={headingRef} tabIndex={-1} className="outline-none">
            {fromSettings ? "Edit household" : "Who lives in your household?"}
          </h1>
          <p className="text-text-2">{privacyNote}</p>
        </div>

        <div className="purvai-card space-y-6 p-6">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {FLAG_OPTIONS.map((option) => {
              const checked = flags[option.kind];
              const inputId = `flag-${option.kind}`;
              return (
                <label
                  key={option.kind}
                  htmlFor={inputId}
                  data-selected={checked}
                  className="purvai-choice-card items-start"
                >
                  <input
                    id={inputId}
                    type="checkbox"
                    checked={checked}
                    onChange={(e) => {
                      setErrorMsg(null);
                      setFlags((prev) => ({ ...prev, [option.kind]: e.target.checked }));
                    }}
                    className="sr-only"
                  />
                  <div className="space-y-0.5">
                    <div className="font-heading text-sm font-medium text-text">{option.label}</div>
                    <div className="text-xs text-text-2">{option.description}</div>
                  </div>
                  <span
                    aria-hidden
                    className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border ${
                      checked
                        ? "border-primary bg-primary text-on-primary"
                        : "border-input-border bg-surface"
                    }`}
                  >
                    {checked && <Check size={14} />}
                  </span>
                </label>
              );
            })}
          </div>

          <div className="flex items-center justify-between border-t border-border pt-4">
            <div>
              <div className="font-heading text-sm font-medium text-text">Adults</div>
              <div className="text-xs text-text-2">General adults in your home</div>
            </div>

            <div className="flex items-center gap-3">
              <button
                type="button"
                aria-label="Decrease adults"
                disabled={adultCount <= 0 || (adultCount === 1 && totalSelected === 1)}
                onClick={() => setAdultCount((c) => Math.max(0, c - 1))}
                className="purvai-btn purvai-btn-secondary min-w-[44px] px-0"
              >
                <Minus size={18} aria-hidden />
              </button>
              <span
                aria-live="polite"
                className="tabular-data min-w-[2ch] text-center text-base font-semibold"
              >
                {adultCount}
              </span>
              <button
                type="button"
                aria-label="Increase adults"
                disabled={adultCount >= 20}
                onClick={() => setAdultCount((c) => Math.min(20, c + 1))}
                className="purvai-btn purvai-btn-secondary min-w-[44px] px-0"
              >
                <Plus size={18} aria-hidden />
              </button>
            </div>
          </div>

          {errorMsg && (
            <p role="alert" className="text-sm text-danger">
              {errorMsg}
            </p>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
            <button
              type="button"
              disabled={saveMutation.isPending}
              onClick={handleContinue}
              className="purvai-btn purvai-btn-primary"
            >
              {fromSettings ? "Save household" : "Continue"}
            </button>

            <button
              type="button"
              onClick={() => {
                void navigate(fromSettings ? "/settings" : "/welcome/location");
              }}
              className="purvai-btn purvai-btn-secondary"
            >
              Back
            </button>
          </div>
        </div>
      </div>
    </OnboardingFrame>
  );
}
