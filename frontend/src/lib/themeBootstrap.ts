import {
  applyReduceMotionToDocument,
  applyThemeToDocument,
  getStoredReduceMotion,
  getStoredTheme,
} from "./theme";

applyThemeToDocument(getStoredTheme());
applyReduceMotionToDocument(getStoredReduceMotion());
