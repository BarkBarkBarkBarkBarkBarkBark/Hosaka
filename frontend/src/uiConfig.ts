// UI appearance preferences — read through the shared sync Store so they
// cross-sync between devices on the appliance build (and stay local-only
// on the hosted build, which is the default Store backend).

import { getStore } from "./sync/store";

export type FontSize = "small" | "normal" | "large";

export type UiConfig = {
  fontSize: FontSize;
};

export const FONT_SIZES: FontSize[] = ["small", "normal", "large"];

export const DEFAULT_UI_CONFIG: UiConfig = {
  fontSize: "normal",
};

export function loadUiConfig(): UiConfig {
  const raw = getStore().get<UiConfig>("ui", DEFAULT_UI_CONFIG);
  // Validate so we don't apply a bogus CSS font-size if a peer somehow
  // wrote a garbage value (or a legacy blob made it through migration).
  return {
    fontSize: (FONT_SIZES as readonly string[]).includes(raw.fontSize ?? "")
      ? (raw.fontSize as FontSize)
      : DEFAULT_UI_CONFIG.fontSize,
  };
}

export function saveUiConfig(cfg: UiConfig): void {
  getStore().update<UiConfig>("ui", DEFAULT_UI_CONFIG, (d) => {
    d.fontSize = cfg.fontSize;
  });
}

// Map font-size values to CSS root font-size percentages.
const FONT_SIZE_SCALE: Record<FontSize, string> = {
  small:  "87.5%",  // ~14px at 16px base
  normal: "100%",
  large:  "112.5%", // ~18px at 16px base
};

// Map font-size values to xterm terminal fontSize (px).
export const FONT_SIZE_TERMINAL: Record<FontSize, number> = {
  small:  11,
  normal: 14,
  large:  17,
};

/**
 * Apply the stored font-size preference to the document root.
 * Call once on boot and again whenever the setting changes.
 */
export function applyFontSize(size: FontSize): void {
  document.documentElement.style.setProperty(
    "--hosaka-font-scale",
    FONT_SIZE_SCALE[size],
  );
  document.documentElement.style.fontSize = FONT_SIZE_SCALE[size];
}
