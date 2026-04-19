import { useEffect, useState } from "react";
import { useTranslation } from "../i18n";

const GLYPHS = ["✿", "❀", "✾", "✽", "❁"] as const;

export function PlantBadge() {
  const { t } = useTranslation("ui");
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => {
      setIdx((n) => (n + 1) % GLYPHS.length);
    }, 4200);
    return () => clearInterval(timer);
  }, []);

  return (
    <span className="plant-badge" title={t("plant.title")}>
      <span className="plant-glyph">{GLYPHS[idx]}</span>
      <span className="plant-label">{t("plant.label")}</span>
    </span>
  );
}
