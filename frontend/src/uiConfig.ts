// UI appearance preferences — stored in localStorage so they survive
// tab refreshes, but are never sent to any server.

export type FontSize = "small" | "normal" | "large";

export type UiConfig = {
  fontSize: FontSize;
};

export const FONT_SIZES: FontSize[] = ["small", "normal", "large"];

const STORAGE_KEY = "hosaka.ui.v1";

export const DEFAULT_UI_CONFIG: UiConfig = {
  fontSize: "normal",
};

export function loadUiConfig(): UiConfig {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_UI_CONFIG };
    const parsed = JSON.parse(raw) as Partial<UiConfig>;
    return {
      fontSize: (FONT_SIZES as readonly string[]).includes(parsed.fontSize ?? "")
        ? (parsed.fontSize as FontSize)
        : DEFAULT_UI_CONFIG.fontSize,
    };
  } catch {
    return { ...DEFAULT_UI_CONFIG };
  }
}

export function saveUiConfig(cfg: UiConfig): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(cfg));
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
