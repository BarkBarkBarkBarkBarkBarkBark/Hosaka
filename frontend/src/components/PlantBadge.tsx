import { useEffect, useState } from "react";
import { useTranslation } from "../i18n";

const GLYPHS = ["✿", "❀", "✾", "✽", "❁"] as const;

export function PlantBadge() {
  const { t } = useTranslation("ui");
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    // Pause the glyph rotation when the kiosk window is not visible.
    // Tiny on its own, but the timer keeps the JS event loop warm + forces
    // React reconciliation forever, which on a Pi 3B+ is real overhead.
    let timer: number | null = null;
    const start = () => {
      if (timer != null) return;
      timer = window.setInterval(() => {
        setIdx((n) => (n + 1) % GLYPHS.length);
      }, 4200);
    };
    const stop = () => {
      if (timer != null) { window.clearInterval(timer); timer = null; }
    };
    if (document.visibilityState === "visible") start();
    const onVis = () => {
      if (document.visibilityState === "visible") start(); else stop();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  return (
    <span className="plant-badge" title={t("plant.title")}>
      <span className="plant-glyph">{GLYPHS[idx]}</span>
      <span className="plant-label">{t("plant.label")}</span>
    </span>
  );
}
