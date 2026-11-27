import { useEffect, useState } from "react";

import { ThemeControl } from "../../components/ThemeControl";
import {
  applyThemeToDocument,
  getStoredTheme,
  setThemePreference,
  type ThemeChoice,
} from "../../lib/theme";

export default function SettingsPage() {
  const [theme, setTheme] = useState<ThemeChoice>(() => getStoredTheme());

  useEffect(() => {
    if (theme !== "system" || typeof window.matchMedia !== "function") {
      return;
    }
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const listener = () => applyThemeToDocument("system");
    media.addEventListener("change", listener);
    return () => media.removeEventListener("change", listener);
  }, [theme]);

  const handleThemeChange = (next: ThemeChoice) => {
    setTheme(next);
    setThemePreference(next);
  };

  return (
    <div className="max-w-[720px] space-y-6">
      <section className="space-y-2">
        <h1>Settings</h1>
        <p className="text-text-2">Manage appearance and workspace preferences.</p>
      </section>

      <section aria-labelledby="appearance-heading" className="purvai-card space-y-4 p-6">
        <div className="space-y-1">
          <h2 id="appearance-heading" className="text-lg font-semibold">
            Appearance
          </h2>
          <p className="text-sm text-text-2">
            Choose Light, Dark, or follow your device setting with System.
          </p>
        </div>

        <ThemeControl value={theme} onChange={handleThemeChange} />
      </section>
    </div>
  );
}
