import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router";

import { ThemeControl } from "../../components/ThemeControl";
import { fetchHealth, fetchHousehold, saveHousehold, type HouseholdResponse } from "../../lib/api";
import {
  applyReduceMotionToDocument,
  applyThemeToDocument,
  getStoredReduceMotion,
  getStoredTheme,
  setThemePreference,
  type ThemeChoice,
} from "../../lib/theme";

const MEMBER_LABELS: Record<string, string> = {
  adult: "Adults",
  child_u12: "Child under 12",
  adult_65p: "Adult over 65",
  heart_lung: "Heart or lung condition",
  outdoor_worker: "Works outdoors",
};

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const householdQuery = useQuery({
    queryKey: ["household"],
    queryFn: fetchHousehold,
    retry: false,
  });

  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    retry: false,
  });

  const [themeOverride, setThemeOverride] = useState<ThemeChoice | null>(null);
  const [reduceMotionOverride, setReduceMotionOverride] = useState<boolean | null>(null);
  const [aiEnabledOverride, setAiEnabledOverride] = useState<boolean | null>(null);
  const [saveChatOverride, setSaveChatOverride] = useState<boolean | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  const theme = themeOverride ?? householdQuery.data?.settings.theme ?? getStoredTheme();
  const reduceMotion =
    reduceMotionOverride ?? householdQuery.data?.settings.reduce_motion ?? getStoredReduceMotion();
  const aiEnabled = aiEnabledOverride ?? householdQuery.data?.settings.ai_enabled ?? true;
  const saveChat = saveChatOverride ?? householdQuery.data?.settings.save_chat ?? false;
  const aiAvailable = healthQuery.data?.ai_available ?? false;

  useEffect(() => {
    if (theme !== "system" || typeof window.matchMedia !== "function") {
      return;
    }
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const listener = () => applyThemeToDocument("system");
    media.addEventListener("change", listener);
    return () => media.removeEventListener("change", listener);
  }, [theme]);

  const updateMutation = useMutation({
    mutationFn: saveHousehold,
    onSuccess: (saved: HouseholdResponse) => {
      queryClient.setQueryData(["household"], saved);
      setThemeOverride(null);
      setReduceMotionOverride(null);
      setAiEnabledOverride(null);
      setSaveChatOverride(null);
      setSaveMessage("Saved");
    },
  });

  const persistSettings = (
    nextTheme: ThemeChoice,
    nextReduceMotion: boolean,
    nextAiEnabled: boolean = aiEnabled,
    nextSaveChat: boolean = saveChat
  ) => {
    const current = householdQuery.data;
    if (!current) return;
    setSaveMessage(null);
    updateMutation.mutate({
      members: current.members,
      location: current.location,
      settings: {
        ...current.settings,
        theme: nextTheme,
        reduce_motion: nextReduceMotion,
        ai_enabled: nextAiEnabled,
        save_chat: nextSaveChat,
      },
    });
  };

  const handleThemeChange = (next: ThemeChoice) => {
    setThemeOverride(next);
    setThemePreference(next);
    persistSettings(next, reduceMotion);
  };

  const handleReduceMotionToggle = () => {
    const next = !reduceMotion;
    setReduceMotionOverride(next);
    applyReduceMotionToDocument(next);
    persistSettings(theme, next);
  };

  const handleAiToggle = () => {
    const next = !aiEnabled;
    setAiEnabledOverride(next);
    persistSettings(theme, reduceMotion, next, saveChat);
  };

  const handleSaveChatToggle = () => {
    const next = !saveChat;
    setSaveChatOverride(next);
    persistSettings(theme, reduceMotion, aiEnabled, next);
  };

  const hh = householdQuery.data;
  const householdSummary = hh
    ? hh.members
        .filter((m) => m.count > 0)
        .map((m) => `${m.count} ${MEMBER_LABELS[m.kind] ?? m.kind}`)
        .join(" · ")
    : "Not set";

  return (
    <div className="max-w-[720px] space-y-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="space-y-1">
          <h1>Settings</h1>
          <p className="text-text-2">Manage appearance, location, and household preferences.</p>
        </div>
        {saveMessage && (
          <span role="status" className="text-xs font-medium text-success">
            {saveMessage}
          </span>
        )}
      </div>

      {/* Appearance & Motion */}
      <section aria-labelledby="appearance-heading" className="purvai-card space-y-5 p-6">
        <div className="space-y-1">
          <h2 id="appearance-heading" className="text-lg font-semibold">
            Appearance
          </h2>
          <p className="text-sm text-text-2">
            Choose Light, Dark, or follow your device setting with System.
          </p>
        </div>

        <ThemeControl value={theme} onChange={handleThemeChange} />

        <div className="flex items-center justify-between gap-4 border-t border-border pt-4">
          <div>
            <div className="font-heading text-sm font-medium text-text">Reduce motion</div>
            <div className="text-xs text-text-2">
              Disable transitions and button press scaling across Purvai.
            </div>
          </div>

          <button
            type="button"
            role="switch"
            aria-checked={reduceMotion}
            aria-label="Reduce motion"
            onClick={handleReduceMotionToggle}
            className={`purvai-btn min-w-[76px] ${
              reduceMotion ? "purvai-btn-primary" : "purvai-btn-secondary"
            }`}
          >
            {reduceMotion ? "On" : "Off"}
          </button>
        </div>
      </section>

      {/* Location & Household */}
      <section aria-labelledby="profile-heading" className="purvai-card space-y-4 p-6">
        <h2 id="profile-heading" className="text-lg font-semibold">
          Location &amp; household
        </h2>

        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-4">
          <div>
            <div className="text-xs font-medium text-muted">Primary location</div>
            <div className="text-sm font-medium text-text">
              {hh ? hh.location.label : "Not configured"}
            </div>
          </div>
          <Link to="/welcome/location?from=settings" className="purvai-btn purvai-btn-secondary">
            Change
          </Link>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-xs font-medium text-muted">Household members</div>
            <div className="text-sm font-medium text-text">{householdSummary}</div>
          </div>
          <Link to="/welcome/household?from=settings" className="purvai-btn purvai-btn-secondary">
            Edit
          </Link>
        </div>
      </section>

      {/* Assistant Preferences */}
      <section aria-labelledby="ai-settings-heading" className="purvai-card space-y-4 p-6">
        <h2 id="ai-settings-heading" className="text-lg font-semibold">
          Assistant preferences
        </h2>

        <div className="space-y-2">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="font-heading text-sm font-medium text-text">AI personalisation</div>
              <div className="text-xs text-text-2">
                {aiAvailable
                  ? "Use Gemini or Groq to reword plans and answer Ask Purvai questions."
                  : "AI is not set up on this server. Standard advice is used."}
              </div>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={aiAvailable ? aiEnabled : false}
              aria-label="AI personalisation"
              disabled={!aiAvailable}
              onClick={handleAiToggle}
              className={`purvai-btn min-w-[76px] ${
                aiAvailable && aiEnabled ? "purvai-btn-primary" : "purvai-btn-secondary"
              }`}
            >
              {aiAvailable && aiEnabled ? "On" : "Off"}
            </button>
          </div>
          <p className="text-xs text-muted">
            Questions are sent to Google Gemini, or Groq as a backup, with air data, your city name
            and household flags only. No name, address or exact location is sent. Free-tier requests
            may be reviewed by people.
          </p>
        </div>

        <div className="flex items-center justify-between gap-4 border-t border-border pt-4">
          <div>
            <div className="font-heading text-sm font-medium text-text">Save chat history</div>
            <div className="text-xs text-text-2">
              Off by default. Store Ask Purvai messages on this device only when enabled.
            </div>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={saveChat}
            aria-label="Save chat history"
            onClick={handleSaveChatToggle}
            className={`purvai-btn min-w-[76px] ${
              saveChat ? "purvai-btn-primary" : "purvai-btn-secondary"
            }`}
          >
            {saveChat ? "On" : "Off"}
          </button>
        </div>
      </section>

      {/* Data Sources & Credits */}
      <section aria-labelledby="credits-heading" className="purvai-card space-y-2 p-6">
        <h2 id="credits-heading" className="text-lg font-semibold">
          Data sources and credits
        </h2>
        <ul className="space-y-1.5 text-sm text-text-2">
          <li>CPCB via data.gov.in — Government Open Data Licence (GODL-India).</li>
          <li>Open-Meteo Air Quality &amp; Geocoding (CAMS) — CC BY 4.0.</li>
        </ul>
      </section>
    </div>
  );
}
