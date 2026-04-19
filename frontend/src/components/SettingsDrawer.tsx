import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  DEFAULT_CONFIG,
  GEMINI_MODELS,
  loadConfig,
  saveConfig,
  type GeminiModel,
  type LlmConfig,
} from "../llm/gemini";
import {
  DEFAULT_AGENT_CONFIG,
  loadAgentConfig,
  saveAgentConfig,
  type AgentConfig,
} from "../llm/agentClient";

type Props = {
  open: boolean;
  onClose: () => void;
};

export function SettingsDrawer({ open, onClose }: Props) {
  const { t } = useTranslation("ui");
  const [cfg, setCfg] = useState<LlmConfig>(loadConfig);
  const [agentCfg, setAgentCfg] = useState<AgentConfig>(loadAgentConfig);
  const [agentPassRevealed, setAgentPassRevealed] = useState(false);
  const [savedFlash, setSavedFlash] = useState(false);

  useEffect(() => {
    if (open) {
      setCfg(loadConfig());
      setAgentCfg(loadAgentConfig());
    }
  }, [open]);

  const flash = () => {
    setSavedFlash(true);
    window.setTimeout(() => setSavedFlash(false), 800);
  };

  const commit = (next: LlmConfig) => {
    setCfg(next);
    saveConfig(next);
    flash();
  };

  const commitAgent = (next: AgentConfig) => {
    setAgentCfg(next);
    saveAgentConfig(next);
    flash();
  };

  if (!open) return null;

  return (
    <div className="drawer-scrim" onClick={onClose}>
      <aside
        className="drawer"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label={t("settings")}
      >
        <header className="drawer-head">
          <h2>
            <span className="panel-glyph">⚙</span> {t("settingsDrawer.heading")}
          </h2>
          <button className="btn btn-ghost" onClick={onClose}>
            {t("settingsDrawer.close")}
          </button>
        </header>

        <section className="drawer-section">
          <h3>{t("settingsDrawer.channel.heading")}</h3>
          <p className="dim small" dangerouslySetInnerHTML={{ __html: t("settingsDrawer.channel.desc") }} />

          <label className="drawer-field">
            <span>{t("settingsDrawer.channel.modelLabel")}</span>
            <select
              value={cfg.model}
              onChange={(e) =>
                commit({ ...cfg, model: e.target.value as GeminiModel })
              }
            >
              {GEMINI_MODELS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>

          <div className="drawer-actions">
            <button
              className="btn btn-ghost"
              onClick={() => commit({ ...DEFAULT_CONFIG })}
            >
              {t("settingsDrawer.reset")}
            </button>
            <span className={`drawer-flash ${savedFlash ? "on" : ""}`}>{t("settingsDrawer.saved")}</span>
          </div>
        </section>

        <section className="drawer-section">
          <h3>{t("settingsDrawer.agent.heading")}</h3>
          <p className="dim small" dangerouslySetInnerHTML={{ __html: t("settingsDrawer.agent.desc") }} />

          <label className="drawer-field">
            <span>{t("settingsDrawer.agent.wsLabel")}</span>
            <input
              type="url"
              placeholder={t("settingsDrawer.agent.wsPlaceholder")}
              value={agentCfg.url}
              onChange={(e) => commitAgent({ ...agentCfg, url: e.target.value.trim() })}
              spellCheck={false}
              autoComplete="off"
            />
          </label>

          <label className="drawer-field">
            <span>{t("settingsDrawer.agent.passLabel")}</span>
            <div className="drawer-key">
              <input
                type={agentPassRevealed ? "text" : "password"}
                placeholder={t("settingsDrawer.agent.passPlaceholder")}
                value={agentCfg.passphrase}
                onChange={(e) =>
                  commitAgent({ ...agentCfg, passphrase: e.target.value })
                }
                spellCheck={false}
                autoComplete="off"
              />
              <button
                className="btn btn-ghost"
                onClick={() => setAgentPassRevealed((r) => !r)}
                type="button"
              >
                {agentPassRevealed ? t("settingsDrawer.agent.hide") : t("settingsDrawer.agent.show")}
              </button>
            </div>
          </label>

          <label className="drawer-field">
            <span>{t("settingsDrawer.agent.channelLabel")}</span>
            <select
              value={agentCfg.enabled ? "on" : "off"}
              onChange={(e) =>
                commitAgent({
                  ...agentCfg,
                  enabled:
                    e.target.value === "on" && !!agentCfg.url && !!agentCfg.passphrase,
                })
              }
            >
              <option value="on">{t("settingsDrawer.agent.channelOn")}</option>
              <option value="off">{t("settingsDrawer.agent.channelOff")}</option>
            </select>
          </label>

          <div className="drawer-actions">
            <button
              className="btn btn-ghost"
              onClick={() => commitAgent({ ...DEFAULT_AGENT_CONFIG })}
            >
              {t("settingsDrawer.reset")}
            </button>
          </div>
        </section>

        <section className="drawer-section dim small">
          <h3>{t("settingsDrawer.storage.heading")}</h3>
          <ul>
            <li dangerouslySetInnerHTML={{ __html: t("settingsDrawer.storage.model") }} />
            <li dangerouslySetInnerHTML={{ __html: t("settingsDrawer.storage.agentCreds") }} />
            <li dangerouslySetInnerHTML={{ __html: t("settingsDrawer.storage.messagesLog") }} />
            <li>{t("settingsDrawer.storage.geminiKey")}</li>
            <li>{t("settingsDrawer.storage.picoclaw")}</li>
          </ul>
        </section>
      </aside>
    </div>
  );
}
