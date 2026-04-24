# sync: per-doc scope & ACL design

Phase 4 design note. **No code in this phase** — this document exists so
the Phase 2/3 sync plumbing stays shaped in a way we can extend into
community-tailnet territory without a rewrite.

## What ships today (Phase 2 + 3)

- One `AutomergeStore` per node. Every connected tailnet peer on the
  user's own tailnet receives and applies every change for every doc.
- Trust model is **"the tailnet is me"**: Tailscale authenticates every
  peer at the network layer, and the implicit assumption is that every
  peer is another device this user owns.
- Docs currently in play:
  - `todo` — open loops
  - `messages` — webhook-sent + echo log
  - `ui` — font size, etc.
  - `lang` — active locale
  - `llm` — non-sensitive provider / model / agent URL
- Sensitive data is kept OFF the sync bus:
  - LLM API keys live server-side in the OS keychain and never hit the
    browser.
  - The hosted agent passphrase is stored in `localStorage` under
    `hosaka.agent.passphrase`, **per device**, never synced.
- Hosted Vercel build opts out entirely: `/api/health` returns
  `nodes_enabled: false`, the `NodesPanel` never mounts, and
  `./sync/repo` is aliased to a no-op stub at bundle time, so Automerge
  WASM isn't even downloaded.

## What Phase 4 needs

Community tailnet introduces **untrusted peers**. Shared recipes, public
presence, multi-writer notes — none of those should let a random
community member read the `todo` doc or write to the `llm` doc.

Four concerns:

1. **Scope** — is this doc private to my devices, or shared with the
   community?
2. **Membership** — which peers may read/write which doc?
3. **At-rest confidentiality** — even on a trusted peer, is the blob on
   disk encrypted?
4. **Key rotation** — if a device leaves the household (sold Pi,
   ex-roommate), can we cut it off?

## Proposed model

### 1. Wire-level scope tag

Today's `WireMessage` already has a `doc` field. Extend it:

```ts
type WireMessage =
  | { type: "hello"; node_id: string; role: "browser" | "peer"; scopes: Scope[] }
  | { type: "snapshot"; doc: DocName; scope: Scope; b64: string; sig?: string }
  | { type: "changes";  doc: DocName; scope: Scope; b64: string; sig?: string };

type Scope =
  | "personal"                 // this user's own devices only
  | `community:${string}`      // a named community doc (e.g. "community:recipes")
```

The relay (`sync_ws.py`) treats the scope as opaque routing info:

- `personal` frames only go out to peers whose `hello` claimed
  `personal` scope AND that we've independently verified are ours (we
  already do — our own tailnet).
- `community:<id>` frames go out to any peer whose `hello` claimed the
  same community id.

### 2. Membership — signed capability tokens

Each node generates an Ed25519 identity key on first boot, stored in
`~/.hosaka/state/node.key`. The node publishes its public key to the
community index (TBD: could be a Fly.io service, could be a DNS TXT
record, could be a Gist — deliberately punted).

Per-doc membership is a JSON "capability" blob signed by the doc's
creator:

```json
{
  "doc": "community:recipes",
  "subject": "<peer pubkey>",
  "perm": "rw" | "r" | "admin",
  "expires": 1780000000,
  "sig": "<ed25519(payload by creator)>"
}
```

Peers present their capability on handshake; the relay drops frames
from peers whose claimed scope isn't in their presented cap set.

This is capability-style, not ACL-list-style, so we don't need a
central auth server. The doc creator is the admin; they hand out caps
by copy/paste or QR.

### 3. At-rest + in-flight confidentiality

Tailscale gives us transport encryption for free. At-rest is still an
issue for `llm` specifically (and any future community docs with
private notes).

Plan:

- One **doc encryption key** (DEK) per synced doc, symmetric (AES-GCM).
- DEK is wrapped with a **key encryption key** (KEK) per member.
  - For `personal` docs, the KEK is derived from a passphrase the user
    enters on first setup of a new device (PBKDF2 / Argon2id into
    SubtleCrypto).
  - For `community:<id>` docs, the KEK is the public key of each
    member; the DEK is sealed-box'd with `crypto_box_seal`-style logic
    for each member, re-sealed on membership change.
- The KEK itself is cached at the OS layer:
  - Python → `keyring` (macOS Keychain / Linux Secret Service / KWallet)
  - Browser → derived fresh per session, never persisted; user re-enters
    on every fresh session.

Change bytes are encrypted in the browser **before** going into
`send()`. The relay never sees plaintext. Snapshots on disk are
ciphertext.

### 4. Key rotation / device eviction

- Admin revokes a cap and publishes the revocation (signed) to the
  community index.
- Admin generates a new DEK, re-wraps it for the remaining members, and
  broadcasts `{type: "dek_rotation", doc, dek_map, prev_version}`.
- Peers that accept the new DEK can still decrypt old changes (they
  keep a small history of DEKs keyed by version); the evicted peer
  cannot decrypt anything from `prev_version + 1` onward.

This is the minimum workable cryptographic model for a "cut off my
sold-Pi" operation without needing an online authority.

## What NOT to build yet

- A central user account system. Identity is per-node Ed25519 keypairs;
  users correlate devices themselves. If a user wants a "profile",
  that's a UI concern, not a protocol one.
- A community index server with strong consistency. First-cut can be
  an append-only log in a public bucket, signed by the admin. We can
  upgrade later.
- Rate limiting / abuse controls. Defer until we have users, not
  hypothetical users.

## Migration checklist when we build it

- Extend `WireMessage` with `scope` and `sig`. Default unspecified to
  `personal` for backwards compat with Phase 2/3 nodes.
- Add a `DocMeta` registry in `repo.ts`: which docs are `personal`,
  which are `community:*`, and what permissions this node has on each.
- Gate the relay in `sync_ws.py` on a presented cap set (new
  `/ws/sync?token=<cap-bundle>` query param or a first-frame cap list).
- Add `~/.hosaka/state/node.key` generation on first boot.
- Build a minimal "invite a device" flow in the Nodes panel: QR code
  of a signed cap; the other device scans, the relay accepts.

## Where this leaves Phase 3

Phase 3 is done as-is. The store abstraction + message envelope are
already loose enough to accept the extra `scope` / `sig` fields without
breaking older clients (unknown fields are simply ignored by the
Automerge-over-WS path). The Python relay is pure fan-out, so adding a
scope-aware routing layer is additive, not a rewrite.

No code changes are needed from this document. It exists so the next
engineer (or future me) doesn't have to reconstruct the reasoning from
scratch.
