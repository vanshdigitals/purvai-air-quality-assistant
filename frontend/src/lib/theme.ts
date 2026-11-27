export type ThemeChoice = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "purvai.theme";
export const REDUCE_MOTION_STORAGE_KEY = "purvai.reduceMotion";

export function isThemeChoice(value: string | null): value is ThemeChoice {
  return value === "light" || value === "dark" || value === "system";
}

export function getStoredTheme(): ThemeChoice {
  try {
    const raw = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isThemeChoice(raw) ? raw : "system";
  } catch {
    return "system";
  }
}

export function resolveTheme(choice: ThemeChoice): ResolvedTheme {
  if (choice === "light" || choice === "dark") {
    return choice;
  }
  if (typeof window.matchMedia === "function") {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return "light";
}

export function applyThemeToDocument(choice: ThemeChoice): ResolvedTheme {
  const resolved = resolveTheme(choice);
  document.documentElement.dataset.theme = resolved;
  return resolved;
}

export function setThemePreference(choice: ThemeChoice): ResolvedTheme {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, choice);
  } catch {
    // Ignore storage errors in restricted contexts.
  }
  return applyThemeToDocument(choice);
}

export function getStoredReduceMotion(): boolean {
  try {
    return window.localStorage.getItem(REDUCE_MOTION_STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

export function applyReduceMotionToDocument(enabled: boolean): void {
  if (enabled) {
    document.documentElement.dataset.reduceMotion = "true";
  } else {
    delete document.documentElement.dataset.reduceMotion;
  }
  try {
    window.localStorage.setItem(REDUCE_MOTION_STORAGE_KEY, String(enabled));
  } catch {
    // Ignore storage errors.
  }
}
