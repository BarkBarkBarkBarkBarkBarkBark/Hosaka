/**
 * Hosaka radio library — public-domain + CC-BY audio fetched from the
 * Internet Archive's `audio` collections. Stored client-side in
 * localStorage for now; a server-side index can take over later without
 * the UI noticing because the consumer surface is just a Track[].
 *
 * Attribution: every track keeps its IA identifier, creator, and source
 * URL so the player can render a "from <creator> via Internet Archive"
 * line per the CC-BY norms. Public-domain items still get attribution
 * because it's nice.
 */

export type Track = {
  id: string;            // unique within the library (IA identifier + file)
  title: string;
  creator: string;
  genre: "classical" | "jazz" | "other";
  source: "internet-archive";
  identifier: string;    // IA identifier
  file: string;          // file name within the IA item
  audioUrl: string;      // direct streamable URL
  detailsUrl: string;    // human-readable IA details page
  license: string;       // free-text from IA (e.g. "Public Domain", "CC BY 3.0")
  attribution: string;   // pre-formatted "Title — Creator (License) via IA"
  durationSeconds?: number;
};

const STORAGE_KEY = "hosaka.radio.library.v1";
const IA_SEARCH = "https://archive.org/advancedsearch.php";
const IA_METADATA = "https://archive.org/metadata";
const IA_DOWNLOAD = "https://archive.org/download";

type IaSearchRow = {
  identifier?: string;
  title?: string | string[];
  creator?: string | string[];
  licenseurl?: string;
  subject?: string | string[];
};

type IaFile = {
  name?: string;
  format?: string;
  length?: string;
  source?: string;
};

function asString(value: string | string[] | undefined, fallback = ""): string {
  if (Array.isArray(value)) return value[0] ?? fallback;
  return value ?? fallback;
}

function loadStoredLibrary(): Track[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Track[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function persistLibrary(tracks: Track[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(tracks));
  } catch {
    // localStorage may be disabled — non-fatal, library just won't survive reload.
  }
  try {
    window.dispatchEvent(new CustomEvent("hosaka:radio-library-changed"));
  } catch { /* SSR */ }
}

export function getLibrary(): Track[] {
  return loadStoredLibrary();
}

export function clearLibrary(): void {
  persistLibrary([]);
}

function dedupe(existing: Track[], next: Track[]): Track[] {
  const seen = new Set(existing.map((t) => t.id));
  const merged = [...existing];
  for (const track of next) {
    if (seen.has(track.id)) continue;
    seen.add(track.id);
    merged.push(track);
  }
  return merged;
}

function pickAudioFile(files: IaFile[]): IaFile | null {
  // Prefer original VBR mp3 / ogg; fall back to any audio file.
  const score = (f: IaFile) => {
    const fmt = (f.format ?? "").toLowerCase();
    if (fmt.includes("vbr mp3")) return 5;
    if (fmt.includes("ogg")) return 4;
    if (fmt.includes("mp3")) return 3;
    if (fmt.includes("flac")) return 2;
    if (fmt.includes("audio")) return 1;
    return 0;
  };
  let best: IaFile | null = null;
  let bestScore = 0;
  for (const f of files) {
    if (!f.name) continue;
    const s = score(f);
    if (s > bestScore) { best = f; bestScore = s; }
  }
  return best;
}

async function fetchTrackForItem(
  identifier: string,
  fallback: { title: string; creator: string; license: string; genre: Track["genre"] },
): Promise<Track | null> {
  try {
    const res = await fetch(`${IA_METADATA}/${encodeURIComponent(identifier)}`);
    if (!res.ok) return null;
    const data = (await res.json()) as { files?: IaFile[]; metadata?: Record<string, unknown> };
    const file = pickAudioFile(Array.isArray(data.files) ? data.files : []);
    if (!file?.name) return null;
    const meta = data.metadata ?? {};
    const title = String(meta.title ?? fallback.title);
    const creator = String(meta.creator ?? fallback.creator);
    const license = String(meta.licenseurl ?? meta.license ?? fallback.license);
    const audioUrl = `${IA_DOWNLOAD}/${encodeURIComponent(identifier)}/${encodeURIComponent(file.name)}`;
    const length = file.length ? Number(file.length) : NaN;
    return {
      id: `${identifier}::${file.name}`,
      title,
      creator,
      genre: fallback.genre,
      source: "internet-archive",
      identifier,
      file: file.name,
      audioUrl,
      detailsUrl: `https://archive.org/details/${encodeURIComponent(identifier)}`,
      license,
      attribution: `${title} — ${creator} (${license || "see source"}) via Internet Archive`,
      durationSeconds: Number.isFinite(length) ? length : undefined,
    };
  } catch {
    return null;
  }
}

/**
 * Populate the library with `count` items from a public-domain / CC IA
 * collection matching the requested genre. Returns the freshly-added
 * tracks (not the full library).
 */
export async function populateLibrary(
  genre: "classical" | "jazz",
  count = 8,
): Promise<{ added: Track[]; total: number; message?: string }> {
  // IA query: opensource_audio collection scopes to free-to-share material.
  const subject = genre === "classical" ? "classical" : "jazz";
  const params = new URLSearchParams({
    q: `collection:(opensource_audio) AND mediatype:(audio) AND subject:(${subject})`,
    "fl[]": "identifier,title,creator,licenseurl,subject",
    rows: String(count),
    output: "json",
    sort: "downloads desc",
  });
  let rows: IaSearchRow[];
  try {
    const res = await fetch(`${IA_SEARCH}?${params.toString()}`);
    if (!res.ok) {
      return { added: [], total: getLibrary().length, message: `IA search failed: http ${res.status}` };
    }
    const data = (await res.json()) as { response?: { docs?: IaSearchRow[] } };
    rows = data.response?.docs ?? [];
  } catch (error) {
    return { added: [], total: getLibrary().length, message: `IA search error: ${(error as Error).message}` };
  }
  const fetched: Track[] = [];
  for (const row of rows) {
    const identifier = asString(row.identifier);
    if (!identifier) continue;
    const track = await fetchTrackForItem(identifier, {
      title: asString(row.title, identifier),
      creator: asString(row.creator, "Unknown"),
      license: row.licenseurl ?? "Public Domain (per IA collection)",
      genre,
    });
    if (track) fetched.push(track);
  }
  const merged = dedupe(loadStoredLibrary(), fetched);
  persistLibrary(merged);
  return { added: fetched, total: merged.length };
}
