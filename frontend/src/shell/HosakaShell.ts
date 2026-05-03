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
  localAgentConfig,
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
import { appendConversationEntry } from "../chat/conversationLog";
import { APP_REGISTRY, resolveAppId } from "../ui/appRegistry";
import {
  formatHosakaAppCommand,
  getHosakaAppById,
  HOSAKA_APPS,
  resolveHosakaAppId,
} from "../apps/hosakaApps";
import {
  getHosakaAppStatus,
  installHosakaApp,
  launchHosakaApp,
  refreshHosakaAppsFromHost,
  searchFlathub,
  stageHosakaAppManifest,
  type HosakaAppHostResponse,
} from "../apps/flatpakBackend";
import { populateLibrary } from "../apps/library";

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

function sameOriginHint(): string {
  try {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${window.location.host}/ws/agent`;
  } catch {
    return "/ws/agent";
  }
}

function prompt(): string {
  return `${CYAN}${PROMPT_HOST}${R}:${BLUE}${PROMPT_CWD}${R} ${AMBER}›${R} `;
}

function pad(s: string, n: number): string {
  if (s.length >= n) return s + "  ";
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
  private cancelSeq = 0;
  private abortController: AbortController | null = null;
  private activeAgent: ReturnType<typeof getAgent> | null = null;
  private promptWrittenByCancel = false;
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
  private readonly stagedCommandListener = (event: Event) => {
    const detail = (event as CustomEvent<{ command?: string; autoSubmit?: boolean }>).detail;
    const command = String(detail?.command ?? "").trim();
    if (!command) return;
    this.clearSuggestion();
    this.replaceBuffer(command);
    if (detail?.autoSubmit) {
      this.submit();
    }
  };

  constructor(private readonly term: Terminal) {}

  start(): void {
    this.writeBanner();
    this.writePrompt();
    this.term.onData((data) => this.onData(data));
    window.addEventListener("hosaka:terminal-stage-command", this.stagedCommandListener as EventListener);
    void this.checkLlmConfig();
  }

  dispose(): void {
    window.removeEventListener("hosaka:terminal-stage-command", this.stagedCommandListener as EventListener);
    if (this.thinkingTimer !== null) {
      window.clearInterval(this.thinkingTimer);
      this.thinkingTimer = null;
    }
    if (this.netscanTimer !== null) {
      window.clearInterval(this.netscanTimer);
      this.netscanTimer = null;
    }
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
        if (this.busy) {
          this.cancelCurrent();
          return;
        }
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
    if (raw === "/cancel" || raw === "/stop") {
      this.cancelCurrent();
      return;
    }

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
      this.finishDispatchPrompt();
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
      case "/devices":
      case "/device":
        await this.handleDevices(arg);
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
      case "/home":
      case "/desktop":
      case "/terminal":
      case "/reading":
      case "/video":
      case "/games":
      case "/wiki":
        this.switchToPanel(cmd.slice(1));
        break;
      case "/apps":
        await this.handleApps();
        break;
      case "/app":
        await this.handleApp(arg);
        break;
      case "/install":
        await this.handleInstall(arg);
        break;
      case "/search":
        await this.handleSearch(arg);
        break;
      case "/store":
        this.switchToPanel("app_store");
        break;
      case "/listen":
        this.switchToPanel("music");
        break;
      case "/library":
        await this.handleLibrary(arg);
        break;
      case "/launch":
        await this.handleLaunch(arg);
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
      case "/configure":
        await this.handleConfigure(arg);
        break;
      case "/code":
        await this.handleCode(arg);
        break;
      case "/reset":
        this.llmHistory = [];
        this.writeln(`  ${GRAY}${st("resetConvo")}${R}`);
        break;
      case "/cancel":
      case "/stop":
        this.cancelCurrent();
        return;
      default:
        this.unknown(cmd);
    }
    this.finishDispatchPrompt();
  }

  private finishDispatchPrompt(): void {
    if (this.promptWrittenByCancel) {
      this.promptWrittenByCancel = false;
      return;
    }
    this.writePrompt();
  }

  private cancelCurrent(): void {
    this.cancelSeq += 1;
    this.stopThinking();
    this.busy = false;
    try { this.abortController?.abort(); } catch { /* noop */ }
    this.abortController = null;
    try { this.activeAgent?.close(); } catch { /* noop */ }
    this.activeAgent = null;
    this.buffer = "";
    this.cursor = 0;
    this.writeln(`^C`);
    this.writeln(`  ${GRAY}cancelled current thought. background work may finish server-side, but this terminal is free.${R}`);
    this.promptWrittenByCancel = true;
    this.writePrompt();
  }

  private async askLlm(userPrompt: string): Promise<void> {
    const cfg = loadLlmConfig();
    const runSeq = this.cancelSeq;
    const controller = new AbortController();
    this.abortController = controller;
    this.busy = true;
    this.startThinking();
    this.safeAppendConversation({
      role: "user",
      source: "shell",
      channel: "text",
      text: userPrompt,
      visibility: "visible",
      appId: "terminal",
    });
    try {
      const res = await askGemini(userPrompt, this.llmHistory, cfg, controller.signal);
      if (runSeq !== this.cancelSeq || controller.signal.aborted) return;
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
      this.safeAppendConversation({
        role: "assistant",
        source: "shell",
        channel: "text",
        text: res.text,
        visibility: "visible",
        appId: "terminal",
      });
    } finally {
      this.stopThinking();
      if (this.abortController === controller) this.abortController = null;
      if (runSeq === this.cancelSeq) this.busy = false;
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
    const runSeq = this.cancelSeq;
    this.busy = true;
    this.startThinking();
    this.safeAppendConversation({
      role: "user",
      source: "agent",
      channel: "text",
      text: userPrompt,
      visibility: "visible",
      appId: "terminal",
    });
    try {
      const agent = getAgent(cfg);
      this.activeAgent = agent;
      let res = await agent.send(userPrompt);
      if (runSeq !== this.cancelSeq) return;
      if (!res.ok && res.code === "unreachable") {
        this.stopThinking();
        this.writeln(`  ${DARK_GRAY}${st("agentWake")}${R}`);
        this.startThinking();
        await new Promise((r) => setTimeout(r, 1500));
        if (runSeq !== this.cancelSeq) return;
        res = await agent.send(userPrompt);
        if (runSeq !== this.cancelSeq) return;
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
      this.safeAppendConversation({
        role: "assistant",
        source: "agent",
        channel: "text",
        text: res.text,
        visibility: "visible",
        appId: "terminal",
      });

      const cmd = this.extractSuggestion(res.text);
      if (cmd) {
        this.suggestion = cmd;
        this.safeAppendConversation({
          role: "system",
          source: "agent",
          channel: "system",
          text: `suggested command: ${cmd}`,
          visibility: "hidden",
          appId: "terminal",
        });
      }
    } finally {
      this.stopThinking();
      if (runSeq === this.cancelSeq) this.busy = false;
      this.activeAgent = null;
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

  private safeAppendConversation(input: Parameters<typeof appendConversationEntry>[0]): void {
    try {
      appendConversationEntry(input);
    } catch (error) {
      console.warn("conversation log append failed", error);
    }
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
    if (sub === "local") {
      saveAgentConfig(localAgentConfig());
      this.writeln(`  ${AMBER}agent url set to local backend.${R} ${GRAY}${sameOriginHint()}${R}`);
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

  private async handleCode(arg: string): Promise<void> {
    const cmd = arg.trim();
    if (cmd) {
      await this.shellPassthrough(cmd, localAgentConfig());
      return;
    }
    this.writeln(`  ${CYAN}/code${R} ${GRAY}is shell mode in the browser build.${R}`);
    this.writeln(`  ${GRAY}Use ${CYAN}!<command>${R}${GRAY} for one-shot commands against the Mac/dev backend.${R}`);
    this.writeln(`  ${GRAY}Examples:${R}`);
    this.writeln(`    ${CYAN}!pwd${R}`);
    this.writeln(`    ${CYAN}!ls -la${R}`);
    this.writeln(`    ${CYAN}!command -v picoclaw && picoclaw --version${R}`);
    this.writeln(`  ${DARK_GRAY}For a fully interactive TTY, use the real macOS Terminal pane/window. This web terminal is non-interactive per command.${R}`);
  }

  private async handleConfigure(arg: string): Promise<void> {
    const target = arg.trim().toLowerCase();
    if (!target || target === "status") {
      this.writeln(`  ${CYAN}configure${R}`);
      this.writeln(`    ${CYAN}/configure picoclaw${R} ${GRAY}check local agent install + onboarding${R}`);
      this.writeln(`    ${CYAN}/configure openclaw${R} ${GRAY}explain the heavier desktop-agent path${R}`);
      this.writeln(`    ${CYAN}/settings${R} ${GRAY}open api key / devices / agent settings drawer${R}`);
      this.writeln(`    ${CYAN}/agent local${R} ${GRAY}point terminal at this dev server's local backend${R}`);
      this.writeln(`    ${CYAN}/code${R} ${GRAY}show local shell usage${R}`);
      return;
    }
    if (target === "openclaw") {
      this.writeln(`  ${CYAN}openclaw configuration${R}`);
      this.writeln(`  ${GRAY}Recommendation: keep ${AMBER}picoclaw${R}${GRAY} as the stable appliance/default backend.${R}`);
      this.writeln(`  ${GRAY}OpenClaw should be the heavier desktop backend once a specific CLI/API is chosen.${R}`);
      this.writeln(`  ${GRAY}That is not a rewrite if Hosaka keeps a small adapter boundary:${R}`);
      this.writeln(`    ${CYAN}agent backend = picoclaw | openclaw${R}`);
      this.writeln(`  ${DARK_GRAY}Today this build has the Picoclaw adapter wired. OpenClaw is a planned adapter slot, not an installed runtime yet.${R}`);
      return;
    }
    if (target !== "picoclaw") {
      this.writeln(`  ${GRAY}unknown configure target:${R} ${target}`);
      this.writeln(`  ${GRAY}try:${R} ${CYAN}/configure picoclaw${R} ${GRAY}or${R} ${CYAN}/configure openclaw${R}`);
      return;
    }

    this.writeln(`  ${CYAN}picoclaw configuration check${R}`);
    this.writeln(`  ${DARK_GRAY}running on the local backend, not the hosted relay…${R}`);
    await this.shellPassthrough(
      "if command -v hosaka >/dev/null 2>&1; then hosaka configure picoclaw --no-onboard; else bash scripts/configure-picoclaw.sh --no-onboard; fi",
      localAgentConfig(),
    );
    this.writeln(`  ${GRAY}For interactive onboarding from a real TTY:${R}`);
    this.writeln(`    ${CYAN}hosaka configure picoclaw --onboard${R}`);
    this.writeln(`  ${DARK_GRAY}After that, restart ${CYAN}hosaka dev -fresh${R}${DARK_GRAY} so the backend inherits the updated PATH/config.${R}`);
  }

  private async handleDevices(arg: string): Promise<void> {
    const sub = arg.trim().toLowerCase();
    if (sub === "open" || sub === "app" || sub === "panel") {
      this.switchToPanel("diagnostics");
      return;
    }

    this.busy = true;
    this.writeln(`  ${AMBER}╭─ /devices ─────────────────────────────────────────╮${R}`);
    this.writeln(`  ${AMBER}│${R} ${GRAY}dusty terminal probe: mic rms + camera luma/delta${R}`);
    this.writeln(`  ${AMBER}╰──────────────────────────────────────────────────────╯${R}`);
    this.writeln(`  ${DARK_GRAY}permission prompts may appear. no media leaves this browser.${R}`);
    this.writeln("");

    try {
      const snapshot = await this.fetchDeviceSnapshot();
      if (snapshot) this.writeDeviceSnapshot(snapshot);

      this.writeln(`  ${CYAN}live probe${R}`);
      const mic = await this.probeMicSignal();
      this.writeln(`    mic    ${mic.ok ? GREEN + "●" : RED + "✗"}${R} ${mic.summary}`);
      if (mic.detail) this.writeln(`           ${DARK_GRAY}${mic.detail}${R}`);

      const cam = await this.probeCameraSignal();
      this.writeln(`    camera ${cam.ok ? GREEN + "●" : RED + "✗"}${R} ${cam.summary}`);
      if (cam.detail) this.writeln(`           ${DARK_GRAY}${cam.detail}${R}`);
      if (cam.ascii) {
        this.writeln(`           ${DARK_GRAY}ascii luma plate:${R}`);
        for (const line of cam.ascii.split("\n")) this.writeln(`           ${DARK_GRAY}${line}${R}`);
      }

      this.writeln("");
      const devices = await this.enumerateBrowserDevices();
      this.writeBrowserDeviceSummary(devices);

      this.writeln("");
      this.writeln(`  ${GRAY}open full app:${R} ${CYAN}/devices open${R} ${GRAY}or click the devices tab.${R}`);
    } finally {
      this.busy = false;
    }
  }

  private async fetchDeviceSnapshot(): Promise<Record<string, any> | null> {
    try {
      const resp = await fetch("/api/v1/diag/snapshot");
      if (!resp.ok) return null;
      return await resp.json() as Record<string, any>;
    } catch {
      return null;
    }
  }

  private writeDeviceSnapshot(snapshot: Record<string, any>): void {
    const per = (snapshot.peripherals ?? {}) as Record<string, any>;
    const system = (snapshot.system ?? {}) as Record<string, any>;
    const network = (snapshot.network ?? {}) as Record<string, any>;
    const primary = (network.primary ?? {}) as Record<string, any>;
    this.writeln(`  ${CYAN}host${R} ${snapshot.hostname ?? "unknown"} ${DARK_GRAY}mode=${snapshot.mode ?? "?"} platform=${system.platform ?? "?"}${R}`);
    this.writeln(`  ${CYAN}net ${R} ${primary.ip ?? primary.tailscale_ip ?? "no ip"} ${DARK_GRAY}${primary.iface ?? "iface ?"}${R}`);
    const names = ["audio", "video", "usb", "bluetooth", "battery"];
    const bits = names.map((name) => {
      const ok = Boolean(per[name]?.available);
      return `${ok ? GREEN + "●" : AMBER + "○"}${R} ${name}`;
    });
    this.writeln(`  ${CYAN}srv ${R} ${bits.join(`${DARK_GRAY} · ${R}`)}`);
    this.writeln("");
  }

  private async enumerateBrowserDevices(): Promise<MediaDeviceInfo[]> {
    if (!navigator.mediaDevices?.enumerateDevices) return [];
    try {
      return await navigator.mediaDevices.enumerateDevices();
    } catch {
      return [];
    }
  }

  private writeBrowserDeviceSummary(devices: MediaDeviceInfo[]): void {
    const audioIn = devices.filter((d) => d.kind === "audioinput");
    const videoIn = devices.filter((d) => d.kind === "videoinput");
    const audioOut = devices.filter((d) => d.kind === "audiooutput");
    const pick = (items: MediaDeviceInfo[]) => items.find((d) => d.deviceId === "default") ?? items[0];
    const label = (device?: MediaDeviceInfo) => device?.label || (device ? `${device.kind} ${device.deviceId.slice(0, 8)}…` : "none");
    this.writeln(`  ${CYAN}browser devices${R}`);
    this.writeln(`    default mic    ${AMBER}${label(pick(audioIn))}${R}`);
    this.writeln(`    default camera ${AMBER}${label(pick(videoIn))}${R}`);
    this.writeln(`    default audio  ${AMBER}${label(pick(audioOut))}${R}`);
    this.writeln(`    counts         ${audioIn.length} mic · ${videoIn.length} camera · ${audioOut.length} output`);
    this.writeln("");
  }

  private async probeMicSignal(): Promise<{ ok: boolean; summary: string; detail?: string }> {
    if (!navigator.mediaDevices?.getUserMedia) {
      return { ok: false, summary: "getUserMedia unavailable" };
    }
    let stream: MediaStream | null = null;
    let ctx: AudioContext | null = null;
    try {
      const AudioCtx = window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!AudioCtx) return { ok: false, summary: "AudioContext unavailable" };
      stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      ctx = new AudioCtx();
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;
      const source = ctx.createMediaStreamSource(stream);
      source.connect(analyser);
      const buf = new Float32Array(analyser.fftSize);
      const samples: number[] = [];
      for (let i = 0; i < 18; i++) {
        await new Promise((resolve) => window.setTimeout(resolve, 70));
        analyser.getFloatTimeDomainData(buf);
        let sum = 0;
        for (const value of buf) sum += value * value;
        samples.push(Math.sqrt(sum / buf.length));
      }
      const peak = Math.max(...samples);
      const avg = samples.reduce((a, b) => a + b, 0) / Math.max(samples.length, 1);
      const active = peak > 0.01;
      const bars = this.sparkline(samples.map((v) => Math.min(1, v * 12)));
      return {
        ok: active,
        summary: active ? `signal present  peak=${peak.toFixed(4)} avg=${avg.toFixed(4)}` : `very quiet / no signal  peak=${peak.toFixed(4)}`,
        detail: bars,
      };
    } catch (exc) {
      return { ok: false, summary: `mic probe failed: ${String(exc)}` };
    } finally {
      stream?.getTracks().forEach((track) => track.stop());
      void ctx?.close().catch(() => undefined);
    }
  }

  private async probeCameraSignal(): Promise<{ ok: boolean; summary: string; detail?: string; ascii?: string }> {
    if (!navigator.mediaDevices?.getUserMedia) {
      return { ok: false, summary: "getUserMedia unavailable" };
    }
    let stream: MediaStream | null = null;
    const video = document.createElement("video");
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 320 }, height: { ideal: 240 } },
        audio: false,
      });
      video.muted = true;
      video.playsInline = true;
      video.srcObject = stream;
      await video.play().catch(() => undefined);
      await new Promise((resolve) => window.setTimeout(resolve, 350));

      const canvas = document.createElement("canvas");
      canvas.width = 96;
      canvas.height = 54;
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      if (!ctx) return { ok: false, summary: "canvas unavailable" };

      const frames: ImageData[] = [];
      const means: number[] = [];
      const variances: number[] = [];
      for (let i = 0; i < 5; i++) {
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const frame = ctx.getImageData(0, 0, canvas.width, canvas.height);
        frames.push(frame);
        const stats = this.lumaStats(frame.data);
        means.push(stats.mean);
        variances.push(stats.variance);
        await new Promise((resolve) => window.setTimeout(resolve, 120));
      }

      const mean = means.reduce((a, b) => a + b, 0) / means.length;
      const variance = variances.reduce((a, b) => a + b, 0) / variances.length;
      const deltas: number[] = [];
      for (let i = 1; i < frames.length; i++) {
        deltas.push(this.frameDelta(frames[i - 1].data, frames[i].data));
      }
      const delta = deltas.reduce((a, b) => a + b, 0) / Math.max(deltas.length, 1);
      const black = mean < 8;
      const flat = variance < 18;
      const dynamic = delta > 0.35;
      const ok = !black && (!flat || dynamic);
      const ascii = this.asciiFrame(frames[frames.length - 1], 32, 12);
      return {
        ok,
        summary: black
          ? `stream is black-ish  luma=${mean.toFixed(1)}`
          : ok
            ? `stream alive  luma=${mean.toFixed(1)} variance=${variance.toFixed(1)} delta=${delta.toFixed(2)}`
            : `stream present but flat  luma=${mean.toFixed(1)} variance=${variance.toFixed(1)} delta=${delta.toFixed(2)}`,
        detail: dynamic ? "dynamic signal detected between frames" : "static frame; wave at camera to raise delta",
        ascii,
      };
    } catch (exc) {
      return { ok: false, summary: `camera probe failed: ${String(exc)}` };
    } finally {
      stream?.getTracks().forEach((track) => track.stop());
      video.srcObject = null;
    }
  }

  private lumaStats(data: Uint8ClampedArray): { mean: number; variance: number } {
    let sum = 0;
    let count = 0;
    for (let i = 0; i < data.length; i += 4) {
      sum += 0.2126 * data[i] + 0.7152 * data[i + 1] + 0.0722 * data[i + 2];
      count += 1;
    }
    const mean = sum / Math.max(count, 1);
    let sq = 0;
    for (let i = 0; i < data.length; i += 4) {
      const y = 0.2126 * data[i] + 0.7152 * data[i + 1] + 0.0722 * data[i + 2];
      sq += (y - mean) * (y - mean);
    }
    return { mean, variance: sq / Math.max(count, 1) };
  }

  private frameDelta(a: Uint8ClampedArray, b: Uint8ClampedArray): number {
    let sum = 0;
    let count = 0;
    const len = Math.min(a.length, b.length);
    for (let i = 0; i < len; i += 16) {
      const ay = 0.2126 * a[i] + 0.7152 * a[i + 1] + 0.0722 * a[i + 2];
      const by = 0.2126 * b[i] + 0.7152 * b[i + 1] + 0.0722 * b[i + 2];
      sum += Math.abs(ay - by);
      count += 1;
    }
    return sum / Math.max(count, 1);
  }

  private asciiFrame(frame: ImageData, width: number, height: number): string {
    const chars = " .:-=+*#%@";
    const srcW = frame.width;
    const srcH = frame.height;
    const lines: string[] = [];
    for (let y = 0; y < height; y++) {
      let line = "";
      const sy = Math.floor((y / height) * srcH);
      for (let x = 0; x < width; x++) {
        const sx = Math.floor((x / width) * srcW);
        const idx = (sy * srcW + sx) * 4;
        const luma = 0.2126 * frame.data[idx] + 0.7152 * frame.data[idx + 1] + 0.0722 * frame.data[idx + 2];
        line += chars[Math.min(chars.length - 1, Math.floor((luma / 256) * chars.length))];
      }
      lines.push(line.replace(/\s+$/g, ""));
    }
    return lines.join("\n");
  }

  private sparkline(values: number[]): string {
    const chars = "▁▂▃▄▅▆▇█";
    return values.map((value) => chars[Math.max(0, Math.min(chars.length - 1, Math.round(value * (chars.length - 1))))]).join("");
  }

  private switchToPanel(name: string): void {
    const result = executeHosakaUiCommand({ id: "ui.open_panel", target: name });
    if (!result.ok) {
      this.writeln(`  ${GRAY}${st("switchTab", { panel: name })}${R}`);
      return;
    }
    this.writeln(`  ${GRAY}${st("panel.opened", { panel: name })}${R}`);
  }

  private async handleApps(): Promise<void> {
    this.writeln(`  ${CYAN}hosaka apps${R}`);
    if (HOSAKA_APPS.length === 0) {
      this.writeln(`  ${GRAY}no hosaka apps are registered yet.${R}`);
      return;
    }
    const statuses = await Promise.all(
      HOSAKA_APPS.map(async (app) => ({ app, status: await getHosakaAppStatus(app.id) })),
    );
    for (const { app, status } of statuses) {
      const installState = status.installed === true
        ? `${GREEN}installed${R}`
        : status.flatpakAvailable === false
          ? `${AMBER}flatpak missing${R}`
          : `${DARK_GRAY}not installed${R}`;
      this.writeln(`  ${AMBER}${app.id}${R} — ${app.name} · ${GRAY}${app.category}${R} · ${installState}`);
    }
  }

  private async handleSearch(arg: string): Promise<void> {
    const q = arg.trim();
    if (!q) {
      this.writeln(`  ${GRAY}usage: /search <query>${R}`);
      return;
    }
    this.writeln(`  ${GRAY}searching flathub for "${q}"…${R}`);
    const res = await searchFlathub(q);
    if (!res.ok) {
      this.writeln(`  ${RED}flathub search failed:${R} ${res.message ?? "unknown error"}`);
      return;
    }
    if (res.hits.length === 0) {
      this.writeln(`  ${GRAY}no matches.${R}`);
      return;
    }
    for (const hit of res.hits.slice(0, 10)) {
      this.writeln(`  ${AMBER}${hit.id}${R} — ${hit.name}`);
      if (hit.summary) this.writeln(`    ${DARK_GRAY}${hit.summary}${R}`);
    }
    this.writeln(`  ${GRAY}stage + install via /store, or:${R} ${CYAN}/install <id-after-staging>${R}`);
  }

  private async handleLibrary(arg: string): Promise<void> {
    const parts = arg.trim().split(/\s+/);
    const sub = parts[0]?.toLowerCase() ?? "";
    if (sub === "populate") {
      const genre = (parts[1] ?? "").toLowerCase();
      if (genre !== "classical" && genre !== "jazz") {
        this.writeln(`  ${GRAY}usage: /library populate <classical|jazz>${R}`);
        return;
      }
      this.writeln(`  ${GRAY}pulling ${genre} from internet archive…${R}`);
      const res = await populateLibrary(genre, 6);
      if (res.added.length === 0) {
        this.writeln(`  ${RED}${res.message ?? "no tracks added."}${R}`);
        return;
      }
      this.writeln(`  ${GREEN}added ${res.added.length} ${genre} track(s).${R} ${GRAY}library has ${res.total}.${R}`);
      this.writeln(`  ${GRAY}open the radio:${R} ${CYAN}/listen${R}`);
      return;
    }
    if (sub === "refresh") {
      await refreshHosakaAppsFromHost();
      this.writeln(`  ${GRAY}refreshed app manifests from host.${R}`);
      return;
    }
    if (sub === "stage") {
      const flatpakId = parts[1] ?? "";
      if (!flatpakId) {
        this.writeln(`  ${GRAY}usage: /library stage <flatpak.id>${R}`);
        return;
      }
      const staged = await stageHosakaAppManifest({ flatpak_id: flatpakId });
      this.writeln(staged.ok
        ? `  ${GREEN}staged${R} ${AMBER}${staged.id}${R} ${GRAY}(${staged.path})${R}`
        : `  ${RED}${staged.message ?? "stage failed"}${R}`);
      return;
    }
    this.writeln(`  ${GRAY}usage:${R}`);
    this.writeln(`    ${CYAN}/library populate <classical|jazz>${R}`);
    this.writeln(`    ${CYAN}/library stage <flatpak.id>${R}`);
    this.writeln(`    ${CYAN}/library refresh${R}`);
  }

  private async handleApp(arg: string): Promise<void> {
    const target = arg.trim();
    if (!target) {
      this.writeln(`  ${GRAY}usage: /app <id>${R}`);
      return;
    }
    const appId = resolveHosakaAppId(target);
    if (!appId) {
      this.writeln(`  ${RED}app not found:${R} ${target}`);
      return;
    }
    const app = getHosakaAppById(appId);
    if (!app) {
      this.writeln(`  ${RED}app not found:${R} ${target}`);
      return;
    }
    const status = await getHosakaAppStatus(appId);
    this.writeln(`  ${CYAN}${app.name}${R} ${DARK_GRAY}(${app.id})${R}`);
    this.writeln(`  ${GRAY}${app.description}${R}`);
    this.writeln(`  provider: ${app.provider}`);
    this.writeln(`  backend: ${app.backend}`);
    this.writeln(`  flatpak id: ${AMBER}${app.flatpak_id}${R}`);
    this.writeln(`  install status: ${status.installed ? `${GREEN}installed${R}` : `${DARK_GRAY}not installed${R}`}`);
    this.writeln(`  install command: ${formatHosakaAppCommand(app.install.command)}`);
    this.writeln(`  launch command: ${formatHosakaAppCommand(app.launch.command)}`);
    this.writeln(`  memory: ${app.memory.profile}`);
    if (app.memory.warning) {
      this.writeln(`  ${AMBER}memory warning:${R} ${app.memory.warning}`);
    }
    this.writeln(`  login required: ${app.account_login_required ? "yes" : "no"}`);
    this.writeln(`  hosaka manages credentials: ${app.hosaka_manages_credentials ? "yes" : "no"}`);
    if (app.permissions_notes.length > 0) {
      this.writeln(`  permissions notes:`);
      for (const note of app.permissions_notes) {
        this.writeln(`    - ${note}`);
      }
    }
    if (app.notes && app.notes.length > 0) {
      this.writeln(`  notes:`);
      for (const note of app.notes) {
        this.writeln(`    - ${note}`);
      }
    }
    this.writeHosakaAppResponse(status);
  }

  private async handleInstall(arg: string): Promise<void> {
    const target = arg.trim();
    if (!target) {
      this.writeln(`  ${GRAY}usage: /install <app>${R}`);
      return;
    }
    const status = await installHosakaApp(target);
    this.writeHosakaAppResponse(status);
    if (status.ok) {
      this.safeAppendConversation({
        role: "system",
        source: "ui",
        channel: "system",
        text: `installed hosaka app ${status.appId ?? target}`,
        visibility: "hidden",
        appId: "terminal",
      });
    }
  }

  private writeHosakaAppResponse(status: HosakaAppHostResponse): void {
    const tone = status.ok ? GREEN : status.manifestFound === false ? RED : GRAY;
    this.writeln(`  ${tone}${status.message}${R}`);
    for (const detail of status.details ?? []) {
      this.writeln(`  ${DARK_GRAY}${detail}${R}`);
    }
    if (status.actionableCommand) {
      this.writeln(`  ${GRAY}next:${R} ${CYAN}${status.actionableCommand}${R}`);
    }
  }

  private async handleLaunch(arg: string): Promise<void> {
    const target = arg.trim();
    if (!target) {
      const launchable = APP_REGISTRY.filter((app) => app.status !== "planned").map((app) => app.id).join(", ");
      this.writeln(`  ${GRAY}usage: /launch <app>${R}`);
      this.writeln(`  ${DARK_GRAY}apps: ${launchable}${R}`);
      return;
    }
    const hosakaAppId = resolveHosakaAppId(target);
    if (hosakaAppId) {
      const status = await launchHosakaApp(hosakaAppId);
      this.writeHosakaAppResponse(status);
      if (status.ok) {
        this.safeAppendConversation({
          role: "system",
          source: "ui",
          channel: "system",
          text: `launched hosaka app ${hosakaAppId}`,
          visibility: "hidden",
          appId: "terminal",
        });
      }
      return;
    }
    const appId = resolveAppId(target);
    if (!appId) {
      this.writeln(`  ${RED}app not found:${R} ${target}`);
      return;
    }
    const result = executeHosakaUiCommand({ id: "ui.open_surface", target: appId, preferredContainer: "window" });
    if (!result.ok) {
      this.writeln(`  ${GRAY}couldn't launch ${appId}.${R}`);
      return;
    }
    this.safeAppendConversation({
      role: "system",
      source: "ui",
      channel: "system",
      text: `launched app ${appId}`,
      visibility: "hidden",
      appId: "terminal",
    });
    this.writeln(`  ${GRAY}launched ${AMBER}${appId}${R}`);
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
