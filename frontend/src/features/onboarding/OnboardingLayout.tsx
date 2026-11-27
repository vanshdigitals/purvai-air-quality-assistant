import { useQuery } from "@tanstack/react-query";
import { Info } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Outlet } from "react-router";

import {
  fetchHealth,
  type CommuteMode,
  type LocationPayload,
  type MemberInput,
} from "../../lib/api";

export interface OnboardingDraft {
  location: LocationPayload | null;
  members: MemberInput[];
  commuteMode: CommuteMode;
}

const DEFAULT_DRAFT: OnboardingDraft = {
  location: null,
  members: [{ kind: "adult", count: 1 }],
  commuteMode: "metro",
};

interface OnboardingFrameProps {
  step: number;
  totalSteps?: number;
  children: ReactNode;
}

export function OnboardingFrame({ step, totalSteps = 4, children }: OnboardingFrameProps) {
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
  });
  const isDemo = health?.mode === "demo";

  return (
    <div className="min-h-screen bg-bg text-text">
      <a href="#main-content" className="purvai-skip-link">
        Skip to main content
      </a>

      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex max-w-[720px] items-center justify-between px-4 py-3">
          <span className="font-heading text-lg font-semibold tracking-tight text-primary">
            Purvai
          </span>
          <span className="tabular-data text-sm font-medium text-text-2">
            Step {step} of {totalSteps}
          </span>
        </div>

        {isDemo && (
          <div
            role="status"
            className="border-t border-border bg-info-tint px-4 py-2 text-sm text-info"
          >
            <div className="mx-auto flex max-w-[720px] items-center gap-2">
              <Info size={18} aria-hidden />
              <span>Demo data resets. Export to keep it.</span>
            </div>
          </div>
        )}
      </header>

      <main id="main-content" tabIndex={-1} className="mx-auto max-w-[720px] px-4 py-8">
        {children}
      </main>
    </div>
  );
}

export interface OnboardingOutletContext {
  draft: OnboardingDraft;
  setDraft: React.Dispatch<React.SetStateAction<OnboardingDraft>>;
}

export function OnboardingLayout() {
  const [draft, setDraft] = useState<OnboardingDraft>(DEFAULT_DRAFT);
  return <Outlet context={{ draft, setDraft }} />;
}
