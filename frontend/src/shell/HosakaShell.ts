import type { Terminal } from "@xterm/xterm";
import i18next from "../i18n";
import {
  BANNER,
  PLANT_STATES,
  ORBS,
  getThinkingFrames,
  getLoreFragments,
} from "./content";
import { getCommands } from "./commands";
import {
  askGemini,
  GEMINI_MODELS,
  loadConfig as loadLlmConfig,
  saveConfig as saveLlmConfig,
  type GeminiModel,
  type LlmMessage,
} from "../llm/gemini";
import {
  DEFAULT_AGENT_URL,
  GATED,
  attemptUnlock,
  getAgent,
  loadAgentConfig,
  saveAgentConfig,
  type AgentConfig,
  type AgentErrorCode,
} from "../llm/agentClient";
import {
  generatePacket,
  packetToRow,
  tableHeader,
  netscanHeader,
  realFrameTag,
  portsLine,
  packetCountLine,
  newPortTracker,
  trackPacket,
} from "./netscan";
import { executeHosakaUiCommand } from "../ui/hosakaUi";

// ANSI helpers
const ESC = "\x1b[";
const R = `${ESC}0m`;
const CYAN = `${ESC}36m`;
const AMBER = `${ESC}38;5;214m`;
const AMBER_DIM = `${ESC}2;38;5;214m`;
const VIOLET = `${ESC}38;5;141m`;
const GRAY = `${ESC}38;5;245m`;
const DARK_GRAY = `${ESC}38;5;240m`;
const GREEN = `${ESC}32m`;
const RED = `${ESC}31m`;
const BLUE = `${ESC}34m`;

const PROMPT_HOST = "hosaka";
const PROMPT_CWD = "/operator";

function prompt(): string {
  return `${CYAN}${PROMPT_HOST}${R}:${BLUE}${PROMPT_CWD}${R} ${AMBER}›${R} `;
}

function pad(s: string, n: number): string {
  if (s.length >= n) return s;
  return s + " ".repeat(n - s.length);
}

function pickRandom<T>(arr: readonly T[]): T {
  return arr[Math.floor(Math.random() * arr.length)];
}

function st(key: string, opts?: Record<string, unknown>): string {
  return i18next.t(key, { ns: "shell", ...opts });
}

export class HosakaShell {
  private buffer = "";
  private cursor = 0;
  private history: string[] = [];
  private histIdx = 0;
  private plantTicks = 0;
  private llmHistory: LlmMessage[] = [];
  private busy = false;
  private thinkingTimer: number | null = null;
  private netscanTimer: number | null = null;
  private suggestion: string | null = null;

  // Inline LLM config flow
  private llmConfigured = true;   // optimistic until checked
  private llmPrompted   = false;  // only prompt once per session
  private inConfigFlow  = false;
  private configMasked  = false;
  private configBuf     = "";
  private configResolve: ((v: string) => void) | null = null;

  constructor(private readonly term: Terminal) {}

  start(): void {
    this.writeBanner();
    this.writePrompt();
    this.term.onData((data) => this.onData(data));
    void this.checkLlmConfig();
  }

  private async checkLlmConfig(): Promise<void> {
    // Hosted/gated builds (terminal.hosaka.xyz) don't run the picoclaw
    // backend on the same origin — there is no /api/llm-key to PATCH and
    // visitors don't own the container. Skip the inline config flow
    // entirely so the magic-word UX isn't intercepted by an API-key prompt.
    if (GATED) {
      this.llmConfigured = true;
      this.llmPrompted = true;
      return;
    }
    try {
      const r = await fetch("/api/llm-key");
      // Treat a missing endpoint as "host doesn't expose this; assume OK".
      // Without this the SPA would offer to configure an LLM that has no
      // backend to receive the PATCH — a confusing dead-end for the user.
      if (!r.ok) {
        this.llmConfigured = true;
        this.llmPrompted = true;
        return;
      }
      const d = await r.json() as { configured?: boolean };
      this.llmConfigured = d.configured ?? false;
    } catch {
      // Network failure (offline, CORS, etc.) — also fail closed-but-quiet.
      this.llmConfigured = true;
      this.llmPrompted = true;
    }
  }

  private writeln(s = ""): void {
    this.term.writeln(s);
  }
  private write(s: string): void {
    this.term.write(s);
  }
  private writePrompt(): void {
    const rows = this.term.rows ?? 24;
    const padRows = Math.floor(rows / 2);
    for (let i = 0; i < padRows; i++) this.writeln("");
    this.term.scrollToBottom();
    this.write(`\x1b[${padRows}A`);
    this.write(prompt());

    if (this.suggestion) {
      this.write(`${DARK_GRAY}${this.suggestion}${R}`);
      this.write(`\x1b[${this.suggestion.length}D`);
    }
  }

  private writeBanner(): void {
    const cols = this.term.cols ?? 80;
    if (cols < 56) {
      this.writeln(`  ${CYAN}▓▒ HOSAKA ▒▓${R}  ${GRAY}${st("banner.compactSteady")}${R}`);
      this.writeln(
        `  ${DARK_GRAY}${st("banner.compactHelp")}  ·  ${VIOLET}${st("banner.compactWhisper")}${R}${DARK_GRAY} ${st("banner.compactOpen")}${R}`,
      );
      this.writeln("");
      return;
    }
    for (const line of BANNER) this.writeln(`${CYAN}${line}${R}`);
    this.writeln("");
    this.writeln(this.renderPlant());
    this.writeln("");
    this.writeln(
      `  ${CYAN}${st("banner.online")}${R}  ${GRAY}${st("banner.steady")}${R}  ${AMBER_DIM}${st("banner.hosted")}${R}`,
    );
    this.writeln(
      `  ${DARK_GRAY}${st("banner.explore")}${R}`,
    );
    this.writeln(
      `  ${DARK_GRAY}${st("banner.shareWord")} ${VIOLET}${st("banner.sayIt")}${R}${DARK_GRAY} ${st("banner.channelOpens")}${R}`,
    );
    this.writeln("");
  }

  private renderPlant(): string {
    const idx = Math.min(
      PLANT_STATES.length - 1,
      Math.floor(this.plantTicks / 5),
    );
    return PLANT_STATES[idx]
      .map((l) => `  ${GREEN}${l}${R}`)
      .join("\r\n");
  }

  private onData(data: string): void {
    // Config flow takes full control of input
    if (this.inConfigFlow) {
      this.handleConfigInput(data);
      return;
    }

    if (data === "\x1b[A") return this.historyPrev();
    if (data === "\x1b[B") return this.historyNext();
    if (data === "\x1b[D") return this.moveLeft();
    if (data === "\x1b[C") return this.moveRight();
    if (data === "\x1b[H" || data === "\x01") return this.moveHome();
    if (data === "\x1b[F" || data === "\x05") return this.moveEnd();

    if (data === "\t" && this.suggestion) {
      this.acceptSuggestion();
      return;
    }

    for (const ch of data) {
      const code = ch.charCodeAt(0);
      if (ch === "\r") {
        if (this.suggestion && this.buffer.length === 0) {
          this.acceptSuggestion();
          return;
        }
        this.clearSuggestion();
        this.submit();
      } else if (ch === "\x7f" || ch === "\b") {
        this.backspace();
      } else if (ch === "\x03") {
        if (this.netscanTimer !== null) {
          this.stopNetscan();
          return;
        }
        this.write("^C");
        this.writeln("");
        this.buffer = "";
        this.cursor = 0;
        this.writePrompt();
      } else if (ch === "\x0c") {
        this.term.clear();
        this.writePrompt();
        this.write(this.buffer);
      } else if (ch === "\x1b" && this.suggestion) {
        this.clearSuggestion();
      } else if (code >= 32 && code !== 127) {
        // First printable char when LLM not configured → offer inline setup
        if (!this.llmConfigured && !this.llmPrompted && !this.busy && this.buffer.length === 0 && ch !== "/") {
          this.llmPrompted = true;
          void this.promptLlmConfig();
          return;
        }
        if (this.suggestion) this.clearSuggestion();
        this.insert(ch);
      }
    }
  }

  // ── inline config flow helpers ──────────────────────────────────────────────

  /** Called by onData when inConfigFlow=true.  Handles typed characters for
   *  readLine() promises: echoes normally or as bullets for masked fields. */
  private handleConfigInput(data: string): void {
    for (const ch of data) {
      const code = ch.charCodeAt(0);
      if (ch === "\r") {
        this.inConfigFlow = false;
        const val = this.configBuf;
        this.configBuf = "";
        this.writeln("");
        this.configResolve?.(val);
        this.configResolve = null;
      } else if (ch === "\x7f" || ch === "\b") {
        if (this.configBuf.length > 0) {
          this.configBuf = this.configBuf.slice(0, -1);
          this.write("\b \b");
        }
      } else if (ch === "\x03") {
        // Ctrl-C cancels the flow
        this.inConfigFlow = false;
        this.configBuf = "";
        this.writeln("");
        this.configResolve?.("");
        this.configResolve = null;
      } else if (code >= 32 && code !== 127) {
        this.configBuf += ch;
        this.write(this.configMasked ? "•" : ch);
      }
    }
  }

  /** Returns a promise that resolves when the user presses Enter. */
  private readLine(masked = false): Promise<string> {
    return new Promise((resolve) => {
      this.inConfigFlow = true;
      this.configMasked = masked;
      this.configBuf    = "";
      this.configResolve = resolve;
    });
  }

  private async promptLlmConfig(): Promise<void> {
    this.busy = true;
    this.writeln("");
    this.writeln(`  ${AMBER}no llm backend configured.${R}`);
    this.write(`  ${GRAY}configure one now?${R} ${CYAN}[Y/n]${R} `);

    const answer = await this.readLine();
    if (answer.trim().toLowerCase() === "n") {
      this.writeln(`  ${GRAY}ok — use ${CYAN}/settings${R}${GRAY} or the gear icon any time.${R}`);
      this.writeln("");
      this.busy = false;
      this.writePrompt();
      return;
    }

    // Provider
    this.writeln(`  ${DARK_GRAY}providers: ${CYAN}openai${R}${DARK_GRAY} / ${CYAN}openai-compatible${R}${DARK_GRAY} (Ollama, local, etc.)${R}`);
    this.write(`  ${GRAY}provider${R} ${DARK_GRAY}[openai]${R}: `);
    const providerRaw = await this.readLine();
    const provider = providerRaw.trim() || "openai";

    // Model
    const defaultModel = provider === "openai" ? "gpt-4o-mini" : "llama3";
    this.write(`  ${GRAY}model${R} ${DARK_GRAY}[${defaultModel}]${R}: `);
    const modelRaw = await this.readLine();
    const model = modelRaw.trim() || defaultModel;

    // Base URL (openai-compatible only)
    let base_url = "";
    if (provider === "openai-compatible") {
      this.write(`  ${GRAY}base url${R} ${DARK_GRAY}[http://localhost:11434/v1]${R}: `);
      const urlRaw = await this.readLine();
      base_url = urlRaw.trim() || "http://localhost:11434/v1";
    }

    // API key (masked — never touches llmHistory or chat context)
    this.write(`  ${GRAY}api key${R} ${DARK_GRAY}(input hidden)${R}: `);
    const api_key = await this.readLine(true);

    if (!api_key.trim()) {
      this.writeln(`  ${RED}no key entered — skipping.${R} ${GRAY}use ${CYAN}/settings${R}${GRAY} to configure later.${R}`);
      this.writeln("");
      this.busy = false;
      this.writePrompt();
      return;
    }

    // Send to server
    this.write(`  ${DARK_GRAY}saving…${R}`);
    try {
      const body = { provider, model, base_url, api_key };
      const r = await fetch("/api/llm-key", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const d = await r.json() as { ok?: boolean };
      this.write("\r\x1b[K");
      if (d.ok) {
        this.llmConfigured = true;
        this.writeln(`  ${GREEN}llm configured.${R} ${GRAY}${provider} / ${model}${R}`);
        this.writeln(`  ${DARK_GRAY}your key is stored on the server and never logged or sent as chat context.${R}`);
      } else {
        this.writeln(`  ${RED}server returned an error.${R} ${GRAY}try the ${CYAN}⚙${R}${GRAY} gear icon instead.${R}`);
      }
    } catch {
      this.write("\r\x1b[K");
      this.writeln(`  ${RED}could not reach server.${R} ${GRAY}try again after ${CYAN}hosaka up${R}${GRAY}.${R}`);
    }

    this.writeln("");
    this.busy = false;
    this.writePrompt();
  }

  // ── editing ────────────────────────────────────────────────────────────────

  private insert(ch: string): void {
    const before = this.buffer.slice(0, this.cursor);
    const after = this.buffer.slice(this.cursor);
    this.buffer = before + ch + after;
    this.cursor += ch.length;
    if (after.length === 0) {
      this.write(ch);
    } else {
      this.write(ch + after + "\x1b[" + after.length + "D");
    }
  }

  private backspace(): void {
    if (this.cursor === 0) return;
    const before = this.buffer.slice(0, this.cursor - 1);
    const after = this.buffer.slice(this.cursor);
    this.buffer = before + after;
    this.cursor -= 1;
    this.write("\b" + after + " " + "\x1b[" + (after.length + 1) + "D");
  }

  private moveLeft(): void {
    if (this.cursor > 0) {
      this.cursor -= 1;
      this.write("\x1b[D");
    }
  }
  private moveRight(): void {
    if (this.cursor < this.buffer.length) {
      this.cursor += 1;
      this.write("\x1b[C");
    }
  }
  private moveHome(): void {
    while (this.cursor > 0) this.moveLeft();
  }
  private moveEnd(): void {
    while (this.cursor < this.buffer.length) this.moveRight();
  }

  private historyPrev(): void {
    if (this.history.length === 0) return;
    this.histIdx = Math.max(0, this.histIdx - 1);
    this.replaceBuffer(this.history[this.histIdx] ?? "");
  }
  private historyNext(): void {
    if (this.history.length === 0) return;
    this.histIdx = Math.min(this.history.length, this.histIdx + 1);
    const v = this.history[this.histIdx] ?? "";
    this.replaceBuffer(v);
  }
  private replaceBuffer(next: string): void {
    this.write("\r" + prompt() + "\x1b[K");
    this.write(next);
    this.buffer = next;
    this.cursor = next.length;
  }

  private submit(): void {
    this.writeln("");
    const raw = this.buffer.trim();
    this.buffer = "";
    this.cursor = 0;

    if (raw.length > 0) {
      this.history.push(raw);
      this.histIdx = this.history.length;
      this.plantTicks += 1;
      void this.dispatch(raw);
      return;
    }
    this.writePrompt();
  }

  private async dispatch(raw: string): Promise<void> {
    if (this.busy) {
      this.writeln(`  ${GRAY}${st("dispatch.busy")}${R}`);
      this.writePrompt();
      return;
    }

    if (raw.startsWith("!")) {
      const cmd = raw.slice(1).trim();
      if (!cmd) {
        this.writeln(`  ${GRAY}${st("dispatch.shellUsage")}${R}`);
        this.writePrompt();
        return;
      }
      const agentCfg = loadAgentConfig();
      if (!agentCfg.enabled) {
        this.writeln(`  ${GRAY}${st("dispatch.shellChannelQuiet")} ${VIOLET}${st("dispatch.whisperFirst")}${R}${GRAY} ${st("dispatch.first")}${R}`);
        this.writePrompt();
        return;
      }
      await this.shellPassthrough(cmd, agentCfg);
      this.writePrompt();
      return;
    }

    if (!raw.startsWith("/")) {
      const agentCfg = loadAgentConfig();
      // Gated hosted build + channel still closed: treat the first plain-text
      // line as a passphrase candidate and let the server decide. The client
      // never learns the password — only the server knows HOSAKA_ACCESS_TOKEN.
      if (GATED && !agentCfg.enabled) {
        const candidate = raw.trim();
        if (!candidate || candidate.length > 128) {
          this.channelClosed();
        } else {
          await this.tryMagicWord(candidate, agentCfg);
        }
        this.writePrompt();
        return;
      }
      if (!agentCfg.enabled) {
        this.channelClosed();
      } else {
        await this.askAgent(raw, agentCfg);
      }
      this.writePrompt();
      return;
    }

    const [cmd, ...rest] = raw.split(/\s+/);
    const arg = rest.join(" ");
    switch (cmd) {
      case "/help":
        this.help();
        break;
      case "/commands":
        this.listCommands();
        break;
      case "/about":
        this.about();
        break;
      case "/status":
        this.status();
        break;
      case "/plant":
        this.writeln(this.renderPlant());
        break;
      case "/orb":
        this.orb();
        break;
      case "/lore":
        this.lore();
        break;
      case "/signal":
        this.writeln(`  ${CYAN}${st("signal.steady")}${R} ${st("signal.persistence")}`);
        this.writeln(`  ${GRAY}${st("signal.relative")}${R}`);
        break;
      case "/clear":
        this.term.clear();
        break;
      case "/echo":
        this.writeln(`  ${arg}`);
        break;
      case "/docs":
        this.writeln(
          `  ${AMBER}https://github.com/BarkBarkBarkBarkBarkBarkBark/Hosaka${R}`,
        );
        break;
      case "/messages":
      case "/terminal":
      case "/reading":
      case "/video":
      case "/games":
      case "/wiki":
        this.switchToPanel(cmd.slice(1));
        break;
      case "/web":
        this.handleWeb(arg);
        break;
      case "/reddit":
        this.openWebPreset("reddit");
        break;
      case "/tiktok":
        this.openWebPreset("tiktok");
        break;
      case "/discord":
        this.openWebPreset("discord");
        break;
      case "/update":
        await this.handleUpdate();
        break;
      case "/read":
        this.handleRead(arg);
        break;
      case "/todo":
        this.handleTodo(arg);
        break;
      case "/books":
        this.handleBooks(arg);
        break;
      case "/netscan":
        await this.netscan();
        break;
      case "/exit":
        this.writeln(`  ${GRAY}${st("exit")}${R}`);
        break;
      case "/ask":
      case "/chat":
        if (arg) {
          await this.askLlm(arg);
        } else {
          this.writeln(`  ${GRAY}${st("ask.usage")}${R}`);
        }
        break;
      case "/model":
        this.handleModel(arg);
        break;
      case "/agent":
        await this.handleAgent(arg);
        break;
      case "/settings":
        this.openSettings();
        break;
      case "/reset":
        this.llmHistory = [];
        this.writeln(`  ${GRAY}${st("resetConvo")}${R}`);
        break;
      default:
        this.unknown(cmd);
    }
    this.writePrompt();
  }

  private async askLlm(userPrompt: string): Promise<void> {
    const cfg = loadLlmConfig();
    this.busy = true;
    this.startThinking();
    try {
      const res = await askGemini(userPrompt, this.llmHistory, cfg);
      this.stopThinking();
      if (!res.ok) {
        this.writeGeminiFallback(res.code);
        return;
      }
      this.llmHistory.push({ role: "user", text: userPrompt });
      this.llmHistory.push({ role: "assistant", text: res.text });
      if (this.llmHistory.length > 16) {
        this.llmHistory = this.llmHistory.slice(-16);
      }
      this.writeln("");
      for (const line of res.text.split("\n")) {
        this.writeln(`  ${line}`);
      }
      this.writeln("");
    } finally {
      this.stopThinking();
      this.busy = false;
    }
  }

  private writeGeminiFallback(code: "proxy_down" | "rate_limited" | "empty" | "unknown"): void {
    this.writeln("");
    switch (code) {
      case "rate_limited":
        this.writeln(`  ${GRAY}${st("gemini.rateLimited")}${R}`);
        break;
      case "proxy_down":
        this.writeln(`  ${GRAY}${st("gemini.proxyDown")}${R}`);
        this.writeln(`  ${GRAY}${st("gemini.proxyDownHint")}${R}`);
        break;
      case "empty":
        this.writeln(`  ${GRAY}${st("gemini.empty")}${R}`);
        break;
      default:
        this.writeln(`  ${GRAY}${st("gemini.unknown")}${R}`);
    }
    this.writeln("");
  }

  private channelClosed(): void {
    this.writeln("");
    this.writeln(`  ${GRAY}${st("channelClosed.line1")} ${AMBER}${st("channelClosed.picoclaw")}${R}${GRAY} ${st("channelClosed.line1b")}${R}`);
    this.writeln(`  ${GRAY}${st("channelClosed.line2")}${R}`);
    this.writeln(`  ${GRAY}${st("channelClosed.line3a")} ${VIOLET}${st("channelClosed.magicWord")}${R}${GRAY} ${st("channelClosed.line3b")}${R}`);
    this.writeln("");
  }

  private handleModel(arg: string): void {
    const cfg = loadLlmConfig();
    if (!arg) {
      this.writeln(`  ${GRAY}${st("model.current")}${R} ${AMBER}${cfg.model}${R}`);
      this.writeln(`  ${GRAY}${st("model.available")}${R}`);
      for (const m of GEMINI_MODELS) this.writeln(`    ${CYAN}${m}${R}`);
      this.writeln(
        `  ${GRAY}${st("model.usage")}${R}`,
      );
      return;
    }
    if (!(GEMINI_MODELS as readonly string[]).includes(arg)) {
      this.writeln(`  ${RED}${st("model.unknownModel")}${R} ${arg}`);
      this.writeln(`  ${GRAY}${st("model.tryOneOf")}${R} ${GEMINI_MODELS.join(", ")}`);
      return;
    }
    saveLlmConfig({ ...cfg, model: arg as GeminiModel });
    this.writeln(`  ${GRAY}${st("model.set")}${R} ${AMBER}${arg}${R}`);
  }

  // Ask the server to validate a candidate passphrase. We never check the
  // word on the client — that would leak it in the JS bundle. Instead we
  // open a probe WebSocket with `?token=<candidate>`; the server runs an
  // hmac.compare_digest and either sends us "hello" (success) or closes
  // with 4401 (unauthorized). Marketing/tone-wise: "the word was heard".
  private async tryMagicWord(candidate: string, cfg: AgentConfig): Promise<void> {
    const url = cfg.url || DEFAULT_AGENT_URL;
    this.writeln("");
    this.writeln(`  ${DARK_GRAY}░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░${R}`);
    this.writeln(`  ${DARK_GRAY}${st("magic.wordSpoken")}${R}`);
    this.writeln(`  ${AMBER}${st("magic.authorizing")}${R}${DARK_GRAY}…${R}`);

    const result = await attemptUnlock(url, candidate);
    if (!result.ok) {
      this.writeln(`  ${DARK_GRAY}░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░${R}`);
      this.writeln("");
      if (result.code === "unauthorized") {
        this.writeln(`  ${RED}${st("magic.notTheWord")}${R} ${GRAY}${st("magic.notTheWordHint")}${R}`);
      } else if (result.code === "not_configured") {
        this.writeln(`  ${RED}${st("magic.notConfigured")}${R}`);
      } else {
        this.writeln(`  ${RED}${st("magic.relayCold")}${R} ${GRAY}${st("magic.relayColdHint")}${R}`);
      }
      this.writeln("");
      return;
    }

    saveAgentConfig({ url, passphrase: candidate, enabled: true });

    this.writeln(`  ${AMBER}${st("magic.connecting")}${R}${DARK_GRAY}…${R}  ${GREEN}${st("magic.channelOpen")}${R}`);
    this.writeln(`  ${DARK_GRAY}░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░${R}`);
    this.writeln("");
    this.writeln(`  ${GRAY}${st("magic.speaking")} ${AMBER}picoclaw${R}${GRAY} ${st("magic.framework")}${R}`);
    this.writeln(`  ${GRAY}${st("magic.sandbox")} ${VIOLET}${st("magic.capabilities")}${R}${GRAY}.${R}`);
    this.writeln("");
    this.writeln(`  ${DARK_GRAY}${st("magic.thingsToTry")}${R}`);
    this.writeln(`    ${CYAN}${st("magic.try1")}${R}`);
    this.writeln(`    ${CYAN}${st("magic.try2")}${R}`);
    this.writeln(`    ${CYAN}${st("magic.try3")}${R}`);
    this.writeln("");
    this.writeln(`  ${DARK_GRAY}${st("magic.slow")} ${VIOLET}${st("magic.slowly")}${R}${DARK_GRAY} ${st("magic.slowSuffix")}${R}`);
    this.writeln(`  ${DARK_GRAY}${st("magic.closeHint")}${R} ${CYAN}${st("magic.closeCmd")}${R}${DARK_GRAY}.${R}`);
    this.writeln("");
  }

  private openSettings(): void {
    try {
      executeHosakaUiCommand({ id: "ui.open_settings" });
      this.writeln(`  ${GRAY}${st("settingsCmd.opened")}${R}`);
    } catch {
      this.writeln(`  ${GRAY}${st("settingsCmd.notAvailable")}${R}`);
    }
  }

  private async askAgent(userPrompt: string, cfg: AgentConfig): Promise<void> {
    this.busy = true;
    this.startThinking();
    try {
      const agent = getAgent(cfg);
      let res = await agent.send(userPrompt);
      if (!res.ok && res.code === "unreachable") {
        this.stopThinking();
        this.writeln(`  ${DARK_GRAY}${st("agentWake")}${R}`);
        this.startThinking();
        await new Promise((r) => setTimeout(r, 1500));
        res = await agent.send(userPrompt);
      }
      this.stopThinking();
      if (!res.ok) {
        this.writeAgentFallback(res.code);
        return;
      }
      this.writeln("");
      for (const line of res.text.split("\n")) {
        this.writeln(`  ${line}`);
      }
      this.writeln("");

      const cmd = this.extractSuggestion(res.text);
      if (cmd) {
        this.suggestion = cmd;
      }
    } finally {
      this.stopThinking();
      this.busy = false;
    }
  }

  private acceptSuggestion(): void {
    if (!this.suggestion) return;
    const text = this.suggestion;
    this.suggestion = null;
    this.write("\r" + prompt() + "\x1b[K");
    this.buffer = text;
    this.cursor = text.length;
    this.write(text);
    this.submit();
  }

  private clearSuggestion(): void {
    if (!this.suggestion) return;
    this.suggestion = null;
    this.write("\r" + prompt() + "\x1b[K");
  }

  private extractSuggestion(text: string): string | null {
    const fenced = /```[^\n]*\n([\s\S]*?)```/.exec(text);
    if (fenced) {
      const code = fenced[1].trim();
      const lines = code.split("\n");
      if (lines.length <= 2 && code.length < 200) {
        return lines[0].trim();
      }
    }
    const inline = /`([^`]{3,120})`/.exec(text);
    if (inline) {
      const cmd = inline[1].trim();
      if (!cmd.includes(" ") || /^[!\/]|^[a-z]+\s/.test(cmd)) {
        return cmd;
      }
    }
    return null;
  }

  private startThinking(): void {
    if (this.thinkingTimer !== null) return;
    let tick = 0;
    const trailers = [".", "..", "...", "…", "·…", "··…"];
    const renderFrame = () => {
      const frames = getThinkingFrames();
      const msg = frames[Math.floor(tick / 4) % frames.length];
      const tail = trailers[tick % trailers.length];
      this.write(`\r\x1b[K  ${DARK_GRAY}${tail} ${msg}${R}`);
      tick += 1;
    };
    renderFrame();
    this.thinkingTimer = window.setInterval(renderFrame, 350);
  }

  private stopThinking(): void {
    if (this.thinkingTimer === null) return;
    window.clearInterval(this.thinkingTimer);
    this.thinkingTimer = null;
    this.write("\r\x1b[K");
  }

  private writeAgentFallback(code: AgentErrorCode): void {
    this.writeln("");
    const key = ({
      not_configured: "notConfigured",
      unauthorized: "unauthorized",
      unreachable: "unreachable",
      timeout: "timeout",
      rate_limited: "rateLimited",
      busy: "busy",
      dropped: "dropped",
      empty: "empty",
    } as Record<string, string>)[code] ?? "default";
    this.writeln(`  ${GRAY}${st(`agentError.${key}`)}${R}`);
    this.writeln("");
  }

  private async handleAgent(arg: string): Promise<void> {
    const cfg = loadAgentConfig();
    const parts = arg.trim().split(/\s+/).filter(Boolean);
    const sub = parts[0] ?? "";

    if (!sub || sub === "status") {
      this.writeln(`  ${GRAY}${st("agent.modeLabel")}${R}    ${cfg.enabled ? AMBER + "on" : GRAY + "off"}${R}`);
      this.writeln(`  ${GRAY}${st("agent.urlLabel")}${R}           ${cfg.url || st("agent.unset")}`);
      this.writeln(
        `  ${GRAY}${st("agent.passLabel")}${R}    ${cfg.passphrase ? "•".repeat(Math.min(cfg.passphrase.length, 10)) : st("agent.unset")}`,
      );
      this.writeln("");
      this.writeln(
        `  ${GRAY}${st("agent.usage")}${R}`,
      );
      return;
    }

    if (sub === "on") {
      if (!cfg.url) {
        this.writeln(
          `  ${RED}${st("agent.cantEnable")}${R}`,
        );
        return;
      }
      saveAgentConfig({ ...cfg, enabled: true });
      this.writeln(`  ${AMBER}${st("agent.modeOn")}${R} ${GRAY}${st("agent.typesToPicoclaw")}${R}`);
      return;
    }
    if (sub === "off") {
      saveAgentConfig({ ...cfg, enabled: false });
      this.writeln(`  ${GRAY}${st("agent.modeOff")}${R}`);
      return;
    }
    if (sub === "url") {
      const value = parts.slice(1).join(" ").trim();
      if (!value) {
        this.writeln(`  ${GRAY}${st("agent.urlUsage")}${R}`);
        return;
      }
      if (!/^wss?:\/\//i.test(value)) {
        this.writeln(`  ${RED}${st("agent.urlInvalid")}${R}`);
        return;
      }
      saveAgentConfig({ ...cfg, url: value });
      this.writeln(`  ${GRAY}${st("agent.urlSaved")}${R}`);
      return;
    }
    if (sub === "passphrase") {
      const value = parts.slice(1).join(" ").trim();
      if (!value) {
        this.writeln(`  ${GRAY}${st("agent.passUsage")}${R}`);
        return;
      }
      saveAgentConfig({ ...cfg, passphrase: value });
      this.writeln(`  ${GRAY}${st("agent.passSaved")}${R}`);
      return;
    }
    if (sub === "test") {
      if (!cfg.url) {
        this.writeln(`  ${GRAY}${st("agent.notTuned")}${R}`);
        return;
      }
      this.writeln(`  ${DARK_GRAY}${st("agent.pinging")}${R}`);
      this.busy = true;
      try {
        const agent = getAgent(cfg);
        const res = await agent.send("say 'signal steady' and nothing else.");
        if (res.ok) {
          this.writeln(`  ${GRAY}${st("agent.reply")}${R} ${res.text.split("\n")[0]}`);
        } else {
          this.writeAgentFallback(res.code);
        }
      } finally {
        this.busy = false;
      }
      return;
    }
    this.writeln(`  ${RED}${st("agent.unknownSub")}${R} ${sub}`);
  }

  private switchToPanel(name: string): void {
    const result = executeHosakaUiCommand({ id: "ui.open_panel", target: name });
    if (!result.ok) {
      this.writeln(`  ${GRAY}${st("switchTab", { panel: name })}${R}`);
      return;
    }
    this.writeln(`  ${GRAY}${st("panel.opened", { panel: name })}${R}`);
  }

  private openWebPreset(presetId: string): void {
    const result = executeHosakaUiCommand({ id: "ui.open_web_preset", preset: presetId });
    if (!result.ok) {
      this.writeln(`  ${GRAY}${st("switchTab", { panel: presetId })}${R}`);
      return;
    }
    this.writeln(`  ${GRAY}${st("webPreset.opening", { preset: presetId })}${R}`);
  }

  private handleWeb(target: string): void {
    const result = executeHosakaUiCommand({ id: "ui.open_web_target", target });
    if (!result.ok) {
      this.writeln(`  ${GRAY}${st("switchTab", { panel: "web" })}${R}`);
      return;
    }
    const trimmed = target.trim();
    if (!trimmed) {
      this.writeln(`  ${GRAY}${st("panel.opened", { panel: "web" })}${R}`);
      return;
    }
    this.writeln(`  ${GRAY}${st("webOpen.opening", { target: trimmed })}${R}`);
  }

  private async handleUpdate(): Promise<void> {
    this.writeln(`  ${GRAY}${st("update.starting")}${R}`);
    try {
      const r = await fetch("/api/v1/system/update", {
        method: "POST",
        credentials: "same-origin",
      });
      const j = (await r.json().catch(() => ({}))) as { ok?: boolean; message?: string };
      if (r.ok && j.ok) {
        this.writeln(`  ${GREEN}${j.message ?? st("update.ok")}${R}`);
        return;
      }
      if (r.status === 403) {
        this.writeln(`  ${GRAY}${st("update.needToken")}${R}`);
        return;
      }
      if (r.status === 401) {
        this.writeln(`  ${GRAY}${st("update.unauthorized")}${R}`);
        return;
      }
      if (r.status === 404) {
        this.writeln(`  ${GRAY}${st("update.noApi")}${R}`);
        return;
      }
      this.writeln(`  ${RED}${j.message ?? st("update.fail")}${R}`);
    } catch {
      this.writeln(`  ${GRAY}${st("update.offline")}${R}`);
    }
  }

  private help(): void {
    this.writeln(
      `  ${CYAN}${st("help.quickStart")}${R} ${st("help.typeAnything")}`,
    );
    this.writeln("");
    const starters: [string, string][] = [
      ["/commands", st("help.listEverything")],
      ["/status", st("help.whatsOnline")],
      ["/plant", st("help.checkPlant")],
      ["/lore", st("help.loreBreadcrumbs")],
      ["/orb", st("help.orbSeesYou")],
      ["/about", st("help.whatIsThis")],
    ];
    for (const [c, d] of starters) {
      this.writeln(`    ${CYAN}${pad(c, 14)}${R}${GRAY}${d}${R}`);
    }
    this.writeln("");
    this.writeln(
      `  ${VIOLET}${st("help.noWrongWay")}${R} ${st("help.experimentFreely")}`,
    );
  }

  private listCommands(): void {
    let currentCat = "";
    const rows = getCommands();
    for (const row of rows) {
      if (row.cat !== currentCat) {
        currentCat = row.cat;
        this.writeln("");
        this.writeln(`  ${AMBER_DIM}── ${currentCat} ──${R}`);
      }
      this.writeln(
        `    ${CYAN}${pad(row.cmd, 18)}${R}${GRAY}${row.desc}${R}`,
      );
    }
    this.writeln("");
    this.writeln(
      `  ${DARK_GRAY}${st("listCommands.hostedNote")}${R}`,
    );
  }

  private status(): void {
    const now = new Date().toISOString().replace("T", " ").slice(0, 19);
    this.writeln(`  ${GRAY}${st("status.host")}${R}       ${AMBER}hosaka/operator${R}`);
    this.writeln(`  ${GRAY}${st("status.mode")}${R}       ${AMBER}${st("status.modeHosted")}${R}  ${DARK_GRAY}${st("status.modeComment")}${R}`);
    this.writeln(`  ${GRAY}${st("status.signalLabel")}${R}     ${GREEN}${st("status.signalSteady")}${R}`);
    this.writeln(`  ${GRAY}${st("status.plantLabel")}${R}      ${GREEN}${this.plantState()}${R}`);
    this.writeln(`  ${GRAY}${st("status.orbLabel")}${R}        ${VIOLET}${st("status.orbWatching")}${R}`);
    this.writeln(`  ${GRAY}${st("status.clockLabel")}${R} ${AMBER}${now}${R}`);
  }

  private plantState(): string {
    const idx = Math.min(
      PLANT_STATES.length - 1,
      Math.floor(this.plantTicks / 5),
    );
    const names = i18next.t("plantNames", { ns: "shell", returnObjects: true }) as unknown as string[];
    return `${names[idx] ?? "stable"} (idx ${idx})`;
  }

  private about(): void {
    this.writeln(`  ${CYAN}${st("about.title")}${R}`);
    this.writeln(`  ${GRAY}${st("about.subtitle")}${R}`);
    this.writeln("");
    this.writeln(`  ${st("about.desc1")}`);
    this.writeln(`  ${st("about.desc2")}`);
    this.writeln("");
    this.writeln(`  ${VIOLET}${st("about.noWrongWay")}${R}`);
  }

  private orb(): void {
    this.writeln("");
    const lines = pickRandom(ORBS);
    for (const l of lines) this.writeln(`  ${VIOLET}${l}${R}`);
    const captions = i18next.t("orbCaptions", { ns: "shell", returnObjects: true }) as unknown as string[];
    this.writeln(`  ${GRAY}${pickRandom(captions)}${R}`);
    this.writeln("");
  }

  private lore(): void {
    this.writeln("");
    const fragments = getLoreFragments();
    const lines = pickRandom(fragments);
    for (const line of lines) {
      this.writeln(`  ${DARK_GRAY}${line}${R}`);
    }
    this.writeln("");
  }

  private handleRead(arg: string): void {
    if (!arg) {
      this.writeln(`  ${AMBER}${st("read.libraryTitle")}${R}`);
      this.writeln("");
      fetch("/reading/collections.json")
        .then((r) => r.json())
        .then((entries: { id: string; summary?: string; description?: string }[]) => {
          for (const e of entries) {
            this.writeln(
              `    ${CYAN}${e.id}${R}  ${GRAY}${e.summary ?? e.description ?? ""}${R}`,
            );
          }
          this.writeln("");
          this.writeln(`  ${GRAY}${st("read.usage")}${R}`);
          this.writePrompt();
        })
        .catch(() => {
          this.writeln(`  ${GRAY}${st("read.libraryQuiet")}${R}`);
          this.writePrompt();
        });
      return;
    }
    if (arg === "order") {
      this.writeln(`  ${GRAY}${st("read.kindleNotTuned")}${R}`);
      this.writeln(`  ${GRAY}${st("read.useLocal")}${R}`);
      return;
    }
    executeHosakaUiCommand({ id: "ui.show_document", slug: arg });
    this.writeln(`  ${GRAY}${st("read.opening", { slug: arg })}${R}`);
  }

  private handleTodo(arg: string): void {
    if (!arg) {
      executeHosakaUiCommand({ id: "ui.open_panel", target: "todo" });
      this.writeln(`  ${GRAY}${st("todoCmd.openedPanel")}${R}`);
      return;
    }
    const parts = arg.split(/\s+/);
    const sub = parts[0];
    if (sub === "add") {
      const text = parts.slice(1).join(" ").trim();
      if (!text) {
        this.writeln(`  ${GRAY}${st("todoCmd.addUsage")}${R}`);
        return;
      }
      executeHosakaUiCommand({ id: "ui.todo_add", text });
      this.writeln(`  ${GRAY}${st("todoCmd.loopOpened")} ${CYAN}${text}${R}`);
      return;
    }
    if (sub === "list") {
      try {
        // Prefer the synced Automerge doc if it has been hydrated by now;
        // fall back to the legacy localStorage blob on a cold boot so the
        // terminal command works even before the TodoPanel has ever been
        // opened (the panel is what triggers the first doc load).
        type ShellLoop = { text: string; closed: boolean };
        let loops: ShellLoop[] = [];
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const repoAny = (window as any).__hosakaRepo as
          | { getDoc: <T>(n: string) => T | null }
          | undefined;
        const syncedDoc = repoAny?.getDoc<{ items: ShellLoop[] }>("todo");
        if (syncedDoc && Array.isArray(syncedDoc.items)) {
          loops = syncedDoc.items;
        } else {
          const raw = localStorage.getItem("hosaka.todo.v1");
          loops = raw ? (JSON.parse(raw) as ShellLoop[]) : [];
        }
        const open = loops.filter((l) => !l.closed);
        if (open.length === 0) {
          this.writeln(`  ${GRAY}${st("todoCmd.noOpenLoops")}${R}`);
          return;
        }
        for (const l of open) {
          this.writeln(`    ${CYAN}○${R} ${l.text}`);
        }
      } catch {
        this.writeln(`  ${GRAY}${st("todoCmd.cantRead")}${R}`);
      }
      return;
    }
    this.writeln(`  ${GRAY}${st("todoCmd.usage")}${R}`);
  }

  private handleBooks(arg: string): void {
    if (!arg) {
      executeHosakaUiCommand({ id: "ui.open_panel", target: "books" });
      this.writeln(`  ${GRAY}${st("booksCmd.openedPanel")}${R}`);
      return;
    }
    executeHosakaUiCommand({ id: "ui.search_books", query: arg });
    this.writeln(`  ${GRAY}${st("booksCmd.searching")} ${CYAN}${arg}${R}`);
  }

  private async shellPassthrough(cmd: string, cfg: AgentConfig): Promise<void> {
    this.busy = true;
    this.writeln(`  ${DARK_GRAY}$ ${cmd}${R}`);
    try {
      const agent = getAgent(cfg);
      const res = await agent.runShell(cmd);
      if (!res.ok) {
        this.writeAgentFallback(res.code);
        return;
      }
      const color = res.exit === 0 ? "" : RED;
      if (res.stdout.trim()) {
        for (const line of res.stdout.trimEnd().split("\n")) {
          this.writeln(`  ${color}${line}${R}`);
        }
      }
      if (res.stderr.trim()) {
        for (const line of res.stderr.trimEnd().split("\n")) {
          this.writeln(`  ${RED}${line}${R}`);
        }
      }
      if (res.exit !== 0) {
        this.writeln(`  ${DARK_GRAY}exit ${res.exit}${R}`);
      }
    } finally {
      this.busy = false;
    }
  }

  private async netscan(): Promise<void> {
    const agentCfg = loadAgentConfig();
    this.writeln(netscanHeader());
    if (!agentCfg.enabled) {
      this.writeln(`  ${DARK_GRAY}${st("netscan.rehearsal")}${R}`);
    }
    this.writeln("");
    this.writeln(tableHeader());

    let tickCount = 0;
    const startTime = Date.now();
    const tracker = newPortTracker();
    const agent = agentCfg.enabled ? getAgent(agentCfg) : null;

    this.writeln("");
    this.writeln("");

    this.netscanTimer = window.setInterval(() => {
      const pkt = generatePacket();
      trackPacket(tracker, pkt);
      tickCount += 1;

      const elapsed = Math.max(1, (Date.now() - startTime) / 1000);
      const rate = Math.round(tickCount / elapsed);

      this.write(`\x1b[2A`);
      this.writeln(`  ${packetToRow(pkt)}`);
      this.write(`\r\x1b[K`);
      this.writeln(portsLine(tracker));
      this.write(`\r\x1b[K`);
      this.write(packetCountLine(tickCount, rate));

      if (agent && tickCount % 15 === 0) {
        void agent.runShell("ss -tunp 2>/dev/null | tail -5").then((r) => {
          if (this.netscanTimer === null) return;
          if (r.ok && r.stdout.trim()) {
            for (const line of r.stdout.trim().split("\n").slice(0, 3)) {
              this.write(`\x1b[2A`);
              this.writeln(`  ${realFrameTag(line)}`);
              this.writeln(portsLine(tracker));
              this.write(packetCountLine(tickCount, Math.round(tickCount / Math.max(1, (Date.now() - startTime) / 1000))));
            }
          }
        });
      }
    }, 120 + Math.floor(Math.random() * 80));
  }

  private stopNetscan(): void {
    if (this.netscanTimer === null) return;
    window.clearInterval(this.netscanTimer);
    this.netscanTimer = null;
    this.writeln("");
    this.writeln("");
    this.writeln(`  ${GRAY}${st("netscan.stopped")}${R}`);
    this.writeln("");
    this.writePrompt();
  }

  private unknown(cmd: string): void {
    this.writeln(`  ${GRAY}${st("unknown.prefix")}${R} ${AMBER}${cmd}${R}`);
    this.writeln(
      `  ${VIOLET}${st("unknown.noWrongWay")}${R} ${st("unknown.tryCommands")}`,
    );
    if (cmd === "/rm" || cmd === "/sudo") {
      this.writeln(`  ${RED}${st("unknown.boldChoice")}${R} ${GRAY}${st("unknown.gladItDidnt")}${R}`);
    }
  }
}
