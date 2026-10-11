import { useEffect, useRef, useState } from "react";
import { useTranslation } from "../i18n";
import { menuOrbs, nextWelcomeIndex } from "../orb";

export function BrowserDemoTerminal({ active, onLore }: {
  active: boolean;
  onLore: () => void;
}) {
  const { t } = useTranslation("gui");
  const [lines, setLines] = useState<string[]>(() => [t("demo.welcome")]);
  const [command, setCommand] = useState("");
  const orb = useRef(0);
  const input = useRef<HTMLInputElement>(null);
  const output = useRef<HTMLPreElement>(null);

  useEffect(() => {
    if (active) input.current?.focus();
    else input.current?.blur();
  }, [active]);

  useEffect(() => {
    if (output.current) output.current.scrollTop = output.current.scrollHeight;
  }, [lines]);

  function submit() {
    const value = command.trim();
    if (!value) return;
    setCommand("");
    if (value === "/clear") {
      setLines([]);
      return;
    }
    let reply: string;
    switch (value) {
      case "/help":
      case "/commands":
        reply = t("demo.help");
        break;
      case "/lore":
        reply = t("demo.lore");
        onLore();
        break;
      case "/orb":
        orb.current = nextWelcomeIndex(orb.current, menuOrbs.length);
        reply = menuOrbs[orb.current];
        break;
      case "/signal":
        reply = t("demo.signal");
        break;
      case "/about":
        reply = t("demo.notice");
        break;
      default:
        reply = t("demo.unsupported");
    }
    setLines((previous) => [...previous, `hosaka:demo > ${value}`, reply].slice(-100));
  }

  return (
    <section className="browser-demo" aria-label={t("demo.title")}>
      <p className="deck-hint">
        {t("demo.notice")}{" "}
        <a href="https://github.com/BarkBarkBarkBarkBarkBarkBark/Hosaka#install-in-one-line" target="_blank" rel="noreferrer">{t("demo.install")}</a>
      </p>
      <pre ref={output} className="browser-demo-output" role="log" aria-live="polite">{lines.join("\n\n")}</pre>
      <form onSubmit={(event) => { event.preventDefault(); submit(); }}>
        <label htmlFor="demo-command">hosaka:demo &gt;</label>
        <input ref={input} id="demo-command" aria-label={t("demo.command")} value={command}
          onChange={(event) => setCommand(event.target.value)} disabled={!active}
          autoComplete="off" autoCapitalize="none" spellCheck={false} maxLength={512} />
        <button type="submit" disabled={!active || !command.trim()}>{t("demo.run")}</button>
      </form>
    </section>
  );
}
