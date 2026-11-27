import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bike, Bus, Car, Check, Footprints, TrainFront } from "lucide-react";
import { useEffect, useRef, useState, type ComponentType } from "react";
import { useNavigate, useOutletContext } from "react-router";

import { saveHousehold, type CommuteMode } from "../../lib/api";
import { getStoredReduceMotion, getStoredTheme } from "../../lib/theme";
import { OnboardingFrame, type OnboardingOutletContext } from "./OnboardingLayout";

interface CommuteTile {
  mode: CommuteMode;
  label: string;
  icon: ComponentType<{ size?: number; "aria-hidden"?: boolean }>;
}

const COMMUTE_TILES: readonly CommuteTile[] = [
  { mode: "metro", label: "Metro", icon: TrainFront },
  { mode: "bus", label: "Bus", icon: Bus },
  { mode: "car", label: "Car", icon: Car },
  { mode: "scooter", label: "Scooter", icon: Bike },
  { mode: "auto", label: "Auto", icon: Car },
  { mode: "cycle", label: "Cycle", icon: Bike },
  { mode: "walk", label: "Walk", icon: Footprints },
];

export default function CommuteStepPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { draft, setDraft } = useOutletContext<OnboardingOutletContext>();
  const headingRef = useRef<HTMLHeadingElement>(null);

  const [selected, setSelected] = useState<CommuteMode>(draft.commuteMode);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!draft.location) {
      void navigate("/welcome/location", { replace: true });
    }
  }, [draft.location, navigate]);

  const finishMutation = useMutation({
    mutationFn: saveHousehold,
    onSuccess: (saved) => {
      queryClient.setQueryData(["household"], saved);
      void navigate("/today", { replace: true });
    },
    onError: (err) => {
      setErrorMsg(err instanceof Error ? err.message : "Could not complete onboarding.");
    },
  });

  const handleToggle = (mode: CommuteMode) => {
    const next: CommuteMode = selected === mode ? "none" : mode;
    setSelected(next);
    setDraft((prev) => ({ ...prev, commuteMode: next }));
  };

  const handleFinish = () => {
    if (!draft.location) return;
    finishMutation.mutate({
      members: draft.members,
      location: draft.location,
      settings: {
        theme: getStoredTheme(),
        commute_mode: selected,
        ai_enabled: true,
        save_chat: false,
        reduce_motion: getStoredReduceMotion(),
      },
    });
  };

  return (
    <OnboardingFrame step={4}>
      <div className="space-y-6">
        <div className="space-y-2">
          <h1 ref={headingRef} tabIndex={-1} className="outline-none">
            How do you usually commute?
          </h1>
          <p className="text-text-2">Pick one travel mode or leave all unselected.</p>
        </div>

        <div className="purvai-card space-y-6 p-6">
          <div
            role="radiogroup"
            aria-label="Commute mode"
            className="grid grid-cols-2 gap-3 sm:grid-cols-4"
          >
            {COMMUTE_TILES.map((tile) => {
              const Icon = tile.icon;
              const isSelected = selected === tile.mode;
              return (
                <button
                  key={tile.mode}
                  type="button"
                  role="radio"
                  aria-checked={isSelected}
                  data-selected={isSelected}
                  onClick={() => handleToggle(tile.mode)}
                  className="purvai-choice-card flex-col items-start gap-2"
                >
                  <div className="flex w-full items-center justify-between">
                    <Icon size={20} aria-hidden />
                    {isSelected && <Check size={16} className="text-primary" aria-hidden />}
                  </div>
                  <span className="font-heading text-sm font-medium">{tile.label}</span>
                </button>
              );
            })}
          </div>

          {errorMsg && (
            <p role="alert" className="text-sm text-danger">
              {errorMsg}
            </p>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
            <button
              type="button"
              disabled={finishMutation.isPending}
              onClick={handleFinish}
              className="purvai-btn purvai-btn-primary"
            >
              {finishMutation.isPending ? "Saving..." : "Finish setup"}
            </button>

            <button
              type="button"
              onClick={() => {
                void navigate("/welcome/household");
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
