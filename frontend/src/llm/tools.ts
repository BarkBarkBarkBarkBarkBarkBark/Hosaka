// Watertight tools exposed to Gemini via function-calling.
//
// Design rules (followed religiously):
//   1. No eval, no Function, no dynamic imports, no fetch, no DOM writes.
//   2. Every tool is pure or only touches a namespaced slice of localStorage.
//   3. Inputs are validated with hand-written guards — no Zod, no runtime deps.
//   4. Outputs are always plain objects, always JSON-safe.
//   5. Errors are values (`{ ok: false, error: "..." }`), never exceptions.
//
// If you add a new tool, keep it inherently safe. If it can't be, don't add
// it here — add it to the server-side picoclaw path instead.

import { getLoreFragments } from "../shell/content";
import { getCommands } from "../shell/commands";

const MEMORY_PREFIX = "hosaka.tools.memory.v1.";
const MEMORY_KEY_MAX = 40;
const MEMORY_VALUE_MAX = 1000;
const MEMORY_MAX_KEYS = 64;

export type ToolResult = Record<string, unknown>;

// Gemini function declaration schema — a subset of OpenAPI the API accepts.
export type GeminiFunctionDeclaration = {
  name: string;
  description: string;
  parameters: {
    type: "object";
    properties: Record<string, unknown>;
    required?: string[];
  };
};

export const GEMINI_TOOL_DECLARATIONS: GeminiFunctionDeclaration[] = [
  {
    name: "get_time",
    description:
      "Return the current time in ISO-8601 UTC and a friendly local-clock string. Takes no arguments.",
    parameters: { type: "object", properties: {} },
  },
  {
    name: "calculate",
    description:
      "Evaluate a simple arithmetic expression. Supports + - * / % ( ) and decimals. Returns the number or an error string. No variables, no functions, no units.",
    parameters: {
      type: "object",
      properties: {
        expression: {
          type: "string",
          description: "e.g. '2 * (3 + 4) / 1.5'",
        },
      },
      required: ["expression"],
    },
  },
  {
    name: "get_lore_fragment",
    description:
      "Return one of Hosaka's canonical lore fragments — short prose from before the cascade. Takes no arguments; picks one at random.",
    parameters: { type: "object", properties: {} },
  },
  {
    name: "list_commands",
    description:
      "Return the taxonomy of slash commands the Hosaka shell supports.",
    parameters: { type: "object", properties: {} },
  },
  {
    name: "whoami",
    description:
      "Return basic, already-public info about the operator's browser: user-agent, language, timezone. No network call, no cookies.",
    parameters: { type: "object", properties: {} },
  },
  {
    name: "remember",
    description:
      "Save a short string to the operator's private browser memory, under a key. Values are kept only in this browser's localStorage and never leave it. Overwrites an existing key.",
    parameters: {
      type: "object",
      properties: {
        key: { type: "string", description: `<=${MEMORY_KEY_MAX} chars, [a-z0-9_-]` },
        value: { type: "string", description: `<=${MEMORY_VALUE_MAX} chars` },
      },
      required: ["key", "value"],
    },
  },
  {
    name: "recall",
    description:
      "Read back a value the operator previously stored with `remember`. Returns {found:false} if the key doesn't exist.",
    parameters: {
      type: "object",
      properties: {
        key: { type: "string", description: `<=${MEMORY_KEY_MAX} chars, [a-z0-9_-]` },
      },
      required: ["key"],
    },
  },
  {
    name: "list_memory",
    description:
      "List the keys currently stored in the operator's private memory. Returns at most 64 keys.",
    parameters: { type: "object", properties: {} },
  },
];

// ── implementations ────────────────────────────────────────────────────────

function ok(data: ToolResult): ToolResult {
  return { ok: true, ...data };
}
function err(message: string): ToolResult {
  return { ok: false, error: message };
}

function validKey(k: unknown): k is string {
  return (
    typeof k === "string" &&
    k.length > 0 &&
    k.length <= MEMORY_KEY_MAX &&
    /^[a-z0-9_-]+$/i.test(k)
  );
}

function validValue(v: unknown): v is string {
  return typeof v === "string" && v.length <= MEMORY_VALUE_MAX;
}

// Safe arithmetic evaluator — tokenize, then Pratt-parse. No `Function`.
function safeCalc(expr: string): number {
  if (expr.length > 200) throw new Error("expression too long");
  const toks: { t: "num" | "op" | "lp" | "rp"; v: string }[] = [];
  const re = /\s*(?:(\d+(?:\.\d+)?)|([+\-*/%])|(\()|(\)))/y;
  re.lastIndex = 0;
  while (re.lastIndex < expr.length) {
    const m = re.exec(expr);
    if (!m) throw new Error(`unexpected character at ${re.lastIndex}`);
    if (m[1] !== undefined) toks.push({ t: "num", v: m[1] });
    else if (m[2] !== undefined) toks.push({ t: "op", v: m[2] });
    else if (m[3] !== undefined) toks.push({ t: "lp", v: "(" });
    else toks.push({ t: "rp", v: ")" });
  }
  let i = 0;
  const peek = () => toks[i];
  const eat = () => toks[i++];
  const prec = (o: string) => (o === "+" || o === "-" ? 1 : 2);
  const apply = (a: number, op: string, b: number) => {
    switch (op) {
      case "+": return a + b;
      case "-": return a - b;
      case "*": return a * b;
      case "/":
        if (b === 0) throw new Error("division by zero");
        return a / b;
      case "%":
        if (b === 0) throw new Error("modulo by zero");
        return a % b;
      default: throw new Error("bad op");
    }
  };
  const parsePrimary = (): number => {
    const t = eat();
    if (!t) throw new Error("unexpected end");
    if (t.t === "num") return parseFloat(t.v);
    if (t.t === "lp") {
      const v = parseExpr(0);
      const r = eat();
      if (!r || r.t !== "rp") throw new Error("missing )");
      return v;
    }
    if (t.t === "op" && (t.v === "+" || t.v === "-")) {
      const v = parsePrimary();
      return t.v === "-" ? -v : v;
    }
    throw new Error(`unexpected token "${t.v}"`);
  };
  const parseExpr = (minPrec: number): number => {
    let lhs = parsePrimary();
    while (true) {
      const t = peek();
      if (!t || t.t !== "op") break;
      const p = prec(t.v);
      if (p < minPrec) break;
      eat();
      const rhs = parseExpr(p + 1);
      lhs = apply(lhs, t.v, rhs);
    }
    return lhs;
  };
  const result = parseExpr(0);
  if (i !== toks.length) throw new Error("trailing tokens");
  if (!Number.isFinite(result)) throw new Error("non-finite result");
  return result;
}

// ── dispatch ───────────────────────────────────────────────────────────────

export type ToolFn = (args: Record<string, unknown>) => ToolResult;

export const TOOL_IMPLS: Record<string, ToolFn> = {
  get_time: () => {
    const now = new Date();
    return ok({
      iso_utc: now.toISOString(),
      local: now.toLocaleString(),
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    });
  },

  calculate: (args) => {
    const expr = args.expression;
    if (typeof expr !== "string") return err("expression must be a string");
    try {
      return ok({ expression: expr, result: safeCalc(expr) });
    } catch (e) {
      return err((e as Error).message);
    }
  },

  get_lore_fragment: () => {
    const frags = getLoreFragments();
    const idx = Math.floor(Math.random() * frags.length);
    return ok({
      index: idx,
      text: frags[idx]!.join("\n"),
    });
  },

  list_commands: () => ok({ commands: getCommands() }),

  whoami: () => {
    const nav = typeof navigator !== "undefined" ? navigator : undefined;
    return ok({
      user_agent: nav?.userAgent ?? "unknown",
      language: nav?.language ?? "unknown",
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      online: nav?.onLine ?? null,
    });
  },

  remember: (args) => {
    if (!validKey(args.key)) return err("invalid key");
    if (!validValue(args.value)) return err("invalid value");
    try {
      const keys = listMemoryKeys();
      if (!keys.includes(args.key as string) && keys.length >= MEMORY_MAX_KEYS) {
        return err(`memory full (${MEMORY_MAX_KEYS} keys max). delete some first.`);
      }
      localStorage.setItem(MEMORY_PREFIX + (args.key as string), args.value as string);
      return ok({ key: args.key, saved: true });
    } catch (e) {
      return err((e as Error).message);
    }
  },

  recall: (args) => {
    if (!validKey(args.key)) return err("invalid key");
    const v = localStorage.getItem(MEMORY_PREFIX + (args.key as string));
    return v === null ? ok({ found: false }) : ok({ found: true, value: v });
  },

  list_memory: () => ok({ keys: listMemoryKeys() }),
};

function listMemoryKeys(): string[] {
  const out: string[] = [];
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i);
    if (k && k.startsWith(MEMORY_PREFIX)) {
      out.push(k.slice(MEMORY_PREFIX.length));
    }
  }
  return out.slice(0, MEMORY_MAX_KEYS);
}

export function runTool(name: string, args: Record<string, unknown>): ToolResult {
  const fn = TOOL_IMPLS[name];
  if (!fn) return err(`unknown tool: ${name}`);
  try {
    return fn(args);
  } catch (e) {
    return err((e as Error).message);
  }
}
