// Theatrical tcpdump / wireshark–style packet generator for /netscan.
// Renders as a live-updating table with a ports summary strip.

const ESC = "\x1b[";
const R = `${ESC}0m`;
const CYAN = `${ESC}36m`;
const GREEN = `${ESC}32m`;
const AMBER = `${ESC}38;5;214m`;
const GRAY = `${ESC}38;5;245m`;
const DARK = `${ESC}38;5;240m`;
const BLUE = `${ESC}34m`;
const RED = `${ESC}31m`;
const VIOLET = `${ESC}38;5;141m`;

const HOSTS = [
  "10.0.42.1", "10.0.42.7", "10.0.42.12", "10.0.42.99",
  "172.16.0.3", "172.16.0.11", "172.16.0.50",
  "192.168.1.1", "192.168.1.42", "192.168.1.100",
  "fd00::412", "fd00::7e:3",
];

const EXT_HOSTS = [
  "relay.hosaka.net", "signal.cascade.io", "orb.deep-signal.dev",
  "node-412.ring.internal", "picoclaw.fly.dev", "cdn.fragment.co",
  "dns.resolver.lan", "ntp.drift.sys",
];

const PORTS = [22, 53, 80, 443, 993, 8080, 8443, 18790, 51820];
const FLAGS = ["SYN", "SYN-ACK", "ACK", "FIN", "PSH-ACK", "RST"];
const DNS_QUERIES = [
  "A orb.deep-signal.dev", "AAAA relay.hosaka.net",
  "PTR 412.42.0.10.in-addr.arpa", "TXT _hosaka.signal.cascade.io",
  "A node-412.ring.internal", "CNAME cdn.fragment.co",
];

function pick<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)];
}

function ts(): string {
  const d = new Date();
  return (
    String(d.getHours()).padStart(2, "0") + ":" +
    String(d.getMinutes()).padStart(2, "0") + ":" +
    String(d.getSeconds()).padStart(2, "0") + "." +
    String(d.getMilliseconds()).padStart(3, "0")
  );
}

function rpad(s: string, n: number): string {
  return s.length >= n ? s.slice(0, n) : s + " ".repeat(n - s.length);
}

export type Packet = {
  time: string;
  proto: string;
  protoColor: string;
  src: string;
  srcPort: number;
  dst: string;
  dstPort: number;
  info: string;
  len: number;
};

function genTcp(): Packet {
  const sp = pick(PORTS);
  const dp = pick(PORTS);
  return {
    time: ts(), proto: "TCP", protoColor: GREEN,
    src: pick(HOSTS), srcPort: sp,
    dst: pick([...HOSTS, ...EXT_HOSTS]), dstPort: dp,
    info: `[${pick(FLAGS)}]`, len: 40 + Math.floor(Math.random() * 1400),
  };
}
function genDns(): Packet {
  return {
    time: ts(), proto: "DNS", protoColor: BLUE,
    src: pick(HOSTS), srcPort: 1024 + Math.floor(Math.random() * 40000),
    dst: "dns.resolver.lan", dstPort: 53,
    info: pick(DNS_QUERIES), len: 40 + Math.floor(Math.random() * 200),
  };
}
function genTls(): Packet {
  const phase = pick(["ClientHello", "ServerHello", "CipherSpec", "AppData"]);
  return {
    time: ts(), proto: "TLS", protoColor: VIOLET,
    src: pick(HOSTS), srcPort: pick(PORTS),
    dst: pick(EXT_HOSTS), dstPort: 443,
    info: phase, len: 80 + Math.floor(Math.random() * 1200),
  };
}
function genIcmp(): Packet {
  return {
    time: ts(), proto: "ICMP", protoColor: AMBER,
    src: pick(HOSTS), srcPort: 0,
    dst: pick([...HOSTS, ...EXT_HOSTS]), dstPort: 0,
    info: pick(["echo req", "echo reply", "unreachable", "time exceeded"]),
    len: 64,
  };
}
function genQuic(): Packet {
  return {
    time: ts(), proto: "QUIC", protoColor: GREEN,
    src: pick(HOSTS), srcPort: pick(PORTS),
    dst: pick(EXT_HOSTS), dstPort: 443,
    info: `DCID=${Math.random().toString(16).slice(2, 10)}`,
    len: 120 + Math.floor(Math.random() * 800),
  };
}
function genSsh(): Packet {
  return {
    time: ts(), proto: "SSH", protoColor: RED,
    src: pick(HOSTS), srcPort: pick(PORTS),
    dst: pick([...HOSTS, ...EXT_HOSTS]), dstPort: 22,
    info: pick(["kex_init", "newkeys", "chan_open", "chan_data"]),
    len: 60 + Math.floor(Math.random() * 300),
  };
}

const GENERATORS = [genTcp, genTcp, genTcp, genDns, genTls, genTls, genIcmp, genQuic, genSsh];

export function generatePacket(): Packet {
  return pick(GENERATORS)();
}

// ── table formatting ──────────────────────────────────────────────────────

const COL_TIME = 12;
const COL_PROTO = 5;
const COL_SRC = 24;
const COL_DST = 24;
const COL_INFO = 16;
const COL_LEN = 6;

const SEP = `${DARK}│${R}`;

export function tableHeader(): string {
  const hdr =
    `${DARK}${rpad("TIME", COL_TIME)}${R}${SEP}` +
    `${DARK}${rpad("PROTO", COL_PROTO)}${R}${SEP}` +
    `${DARK}${rpad("SOURCE", COL_SRC)}${R}${SEP}` +
    `${DARK}${rpad("DESTINATION", COL_DST)}${R}${SEP}` +
    `${DARK}${rpad("INFO", COL_INFO)}${R}${SEP}` +
    `${DARK}${rpad("LEN", COL_LEN)}${R}`;
  const rule = `${DARK}${"─".repeat(COL_TIME)}┼${"─".repeat(COL_PROTO)}┼${"─".repeat(COL_SRC)}┼${"─".repeat(COL_DST)}┼${"─".repeat(COL_INFO)}┼${"─".repeat(COL_LEN)}${R}`;
  return `  ${hdr}\r\n  ${rule}`;
}

export function packetToRow(p: Packet): string {
  const srcStr = p.srcPort ? `${p.src}:${p.srcPort}` : p.src;
  const dstStr = p.dstPort ? `${p.dst}:${p.dstPort}` : p.dst;
  return (
    `${DARK}${rpad(p.time, COL_TIME)}${R}${SEP}` +
    `${p.protoColor}${rpad(p.proto, COL_PROTO)}${R}${SEP}` +
    `${CYAN}${rpad(srcStr, COL_SRC)}${R}${SEP}` +
    `${CYAN}${rpad(dstStr, COL_DST)}${R}${SEP}` +
    `${GRAY}${rpad(p.info, COL_INFO)}${R}${SEP}` +
    `${DARK}${rpad(String(p.len), COL_LEN)}${R}`
  );
}

// ── ports summary ─────────────────────────────────────────────────────────

export type PortTracker = {
  seen: Map<number, { count: number; proto: string; lastSrc: string }>;
};

export function newPortTracker(): PortTracker {
  return { seen: new Map() };
}

export function trackPacket(tracker: PortTracker, p: Packet): void {
  for (const port of [p.srcPort, p.dstPort]) {
    if (!port) continue;
    const existing = tracker.seen.get(port);
    if (existing) {
      existing.count += 1;
      existing.lastSrc = p.src;
    } else {
      tracker.seen.set(port, { count: 1, proto: p.proto, lastSrc: p.src });
    }
  }
}

export function portsLine(tracker: PortTracker): string {
  const sorted = [...tracker.seen.entries()]
    .sort((a, b) => b[1].count - a[1].count)
    .slice(0, 8);
  const parts = sorted.map(([port, info]) => {
    const color = info.count > 10 ? GREEN : info.count > 3 ? AMBER : GRAY;
    return `${color}${port}${R}${DARK}(${info.count})${R}`;
  });
  return `  ${DARK}open ports:${R} ${parts.join(`${DARK} · ${R}`)}`;
}

export function packetCountLine(total: number, perSec: number): string {
  return `  ${DARK}packets: ${AMBER}${total}${R}${DARK}  ~${perSec}/s  ctrl-c to stop${R}`;
}

export function netscanHeader(): string {
  return [
    `  ${DARK}┌─ netscan ─────────────────────────────────────────────────────────────────────────┐${R}`,
    `  ${DARK}│${R} ${GRAY}live packet capture · TCP DNS TLS ICMP QUIC SSH${R}`,
    `  ${DARK}└────────────────────────────────────────────────────────────────────────────────────┘${R}`,
  ].join("\r\n");
}

export function realFrameTag(line: string): string {
  return `${AMBER}[REAL]${R} ${line}`;
}
