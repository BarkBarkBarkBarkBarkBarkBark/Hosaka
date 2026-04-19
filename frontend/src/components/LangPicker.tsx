import { useTranslation } from "react-i18next";

const LANGS = [
  { code: "en", label: "EN" },
  { code: "it", label: "IT" },
  { code: "es", label: "ES" },
  { code: "ja", label: "JA" },
  { code: "fr", label: "FR" },
  { code: "pt", label: "PT" },
] as const;

export function LangPicker() {
  const { i18n } = useTranslation();
  const current = i18n.language?.split("-")[0] ?? "en";

  return (
    <select
      className="lang-picker"
      value={current}
      onChange={(e) => void i18n.changeLanguage(e.target.value)}
      aria-label="language"
    >
      {LANGS.map((l) => (
        <option key={l.code} value={l.code}>
          {l.label}
        </option>
      ))}
    </select>
  );
}
