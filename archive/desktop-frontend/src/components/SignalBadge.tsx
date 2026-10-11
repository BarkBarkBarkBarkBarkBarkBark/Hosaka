import { useTranslation } from "../i18n";

type Props = { label: string };

export function SignalBadge({ label }: Props) {
  const { t } = useTranslation("ui");
  return (
    <span className="signal-badge" title={t("signal.title")}>
      <span className="signal-dot" aria-hidden />
      <span className="signal-label">{label}</span>
    </span>
  );
}
