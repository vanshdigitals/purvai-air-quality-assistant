/* global console, process */
import fs from "node:fs";
import path from "node:path";

const TOKENS_PATH = path.resolve(import.meta.dirname, "..", "src", "styles", "tokens.css");
const css = fs.readFileSync(TOKENS_PATH, "utf-8");

function parseThemeTokens(blockText) {
  const map = {};
  for (const match of blockText.matchAll(/(--[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*;/g)) {
    map[match[1]] = match[2].toLowerCase();
  }
  return map;
}

const lightMatch = css.match(/:root\s*\{([\s\S]*?)\n\}/);
const darkMatch = css.match(/\[data-theme="dark"\]\s*\{([\s\S]*?)\n\}/);
if (!lightMatch || !darkMatch) {
  console.error("Failed to parse :root or [data-theme=dark] blocks in tokens.css");
  process.exit(1);
}

const themes = {
  light: parseThemeTokens(lightMatch[1]),
  dark: parseThemeTokens(darkMatch[1]),
};

function srgbToLinear(c) {
  const v = c / 255;
  return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
}

function relativeLuminance(hex) {
  const r = Number.parseInt(hex.slice(1, 3), 16);
  const g = Number.parseInt(hex.slice(3, 5), 16);
  const b = Number.parseInt(hex.slice(5, 7), 16);
  return 0.2126 * srgbToLinear(r) + 0.7152 * srgbToLinear(g) + 0.0722 * srgbToLinear(b);
}

function contrastRatio(hex1, hex2) {
  const l1 = relativeLuminance(hex1);
  const l2 = relativeLuminance(hex2);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

const PAIRS = [
  ["--text", "--bg", 4.5],
  ["--text", "--surface", 4.5],
  ["--text", "--subtle", 4.5],
  ["--text-2", "--bg", 4.5],
  ["--text-2", "--surface", 4.5],
  ["--muted", "--surface", 4.5],
  ["--on-primary", "--primary", 4.5],
  ["--on-danger", "--danger", 4.5],
  ["--danger", "--danger-tint", 4.5],
  ["--warning", "--warning-tint", 4.5],
  ["--success", "--success-tint", 4.5],
  ["--info", "--info-tint", 4.5],
  ["--text", "--secondary", 4.5],
];

let failed = false;
for (const [themeName, tokens] of Object.entries(themes)) {
  for (const [fg, bg, minRatio] of PAIRS) {
    const fgHex = tokens[fg];
    const bgHex = tokens[bg];
    if (!fgHex || !bgHex) {
      console.error(`[${themeName}] Missing token for ${fg} or ${bg}`);
      failed = true;
      continue;
    }
    const ratio = contrastRatio(fgHex, bgHex);
    const status = ratio >= minRatio ? "PASS" : "FAIL";
    console.log(
      `[${themeName}] ${fg} (${fgHex}) on ${bg} (${bgHex}) = ${ratio.toFixed(2)}:1 [${status}]`
    );
    if (ratio < minRatio) {
      failed = true;
    }
  }
}

if (failed) {
  process.exit(1);
}
