# install.hosaka.xyz

One-line installer for the Hosaka client. Ships the `hosaka` CLI, which
wraps a Docker container and optionally links over a tailnet to a
dedicated Hosaka machine.

## Public install commands

```bash
# mac + linux
curl -fsSL https://install.hosaka.xyz | sh

# windows (PowerShell)
iwr https://install.hosaka.xyz/windows | iex
```

Both drop a `hosaka` executable on the user's PATH and warm up the
container image in the background.

## What the user gets

| Command                       | Effect                                                         |
| ----------------------------- | -------------------------------------------------------------- |
| `hosaka up`                   | Start the local node (web UI on `http://127.0.0.1:8421`)       |
| `hosaka tui`                  | Drop into the console TUI                                      |
| `hosaka open`                 | Open the web UI in the browser                                 |
| `hosaka link <host[:port]>`   | Route `tui` / `open` at a remote Hosaka on the tailnet         |
| `hosaka unlink`               | Go back to the local node                                      |
| `hosaka update`               | `docker pull` the latest image                                 |
| `hosaka status`               | What's running + where it points                               |
| `hosaka uninstall`            | Remove launcher (keeps `~/.hosaka` state)                      |

## Repo layout

```
install/
├── install.sh         # curl | sh — mac + linux
├── install.ps1        # iwr | iex — windows
├── bin/
│   ├── hosaka         # posix launcher (bash)
│   ├── hosaka.cmd     # windows shim → hosaka.ps1
│   └── hosaka.ps1     # windows launcher
└── README.md          # this file
```

Both installers fetch the right launcher file(s) from
`https://install.hosaka.xyz/bin/<name>` at install time, so **the
launcher can ship new versions without re-running the installer** —
`hosaka update` also re-pulls the image.

## Hosting

Anywhere that serves static files over HTTPS works. Pick one and point
`install.hosaka.xyz` at it.

### Option A: Cloudflare Pages (recommended, free)

1. Create a new Pages project backed by this repo's `install/` directory.
2. Set the build output to `install/`.
3. Add a `_redirects` file (already works because of Cloudflare's
   default routing):

   ```
   /            /install.sh   200
   /windows     /install.ps1  200
   ```

4. Add a custom domain `install.hosaka.xyz`.
5. DNS: `CNAME install.hosaka.xyz → <project>.pages.dev` (proxied).

### Option B: GitHub Pages + Cloudflare

1. `gh-pages` branch that mirrors `install/`.
2. Custom domain `install.hosaka.xyz`.
3. Cloudflare proxied CNAME, with a worker (or `_redirects` via a CF
   Pages shim) to rewrite `/` → `install.sh` and `/windows` → `install.ps1`.

### Minimum Cloudflare Worker (if you'd rather skip Pages)

```js
export default {
  async fetch(req) {
    const url = new URL(req.url);
    const base = "https://raw.githubusercontent.com/BarkBarkBarkBarkBarkBarkBark/Hosaka/main/install";
    const map = {
      "/":        `${base}/install.sh`,
      "/windows": `${base}/install.ps1`,
    };
    const direct = map[url.pathname];
    if (direct) return fetch(direct, { headers: { "cache-control": "public, max-age=300" } });
    if (url.pathname.startsWith("/bin/")) return fetch(`${base}${url.pathname}`);
    return new Response("not found", { status: 404 });
  },
};
```

Bind that Worker to `install.hosaka.xyz/*`. Done.

## Image registry

The launcher pulls `ghcr.io/barkbarkbarkbarkbarkbarkbark/hosaka:latest`
by default. Publish from CI with a workflow like:

```yaml
# .github/workflows/image.yml
name: image
on:
  push: { tags: ["v*"] }
  workflow_dispatch:
jobs:
  build:
    runs-on: ubuntu-latest
    permissions: { contents: read, packages: write }
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-qemu-action@v3
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          context: .
          file: docker/Dockerfile
          platforms: linux/amd64,linux/arm64
          push: true
          tags: |
            ghcr.io/barkbarkbarkbarkbarkbarkbark/hosaka:latest
            ghcr.io/barkbarkbarkbarkbarkbarkbark/hosaka:${{ github.ref_name }}
```

Make the package public from the GitHub UI (Packages → hosaka →
Settings → Change visibility → Public) so anonymous `docker pull`
works.

## Verifying locally

```bash
# pretend install.hosaka.xyz is your checkout
python -m http.server 8000 --directory install &

HOSAKA_NO_PULL=1 \
HOSAKA_PREFIX="$HOME/.local" \
curl -fsSL http://127.0.0.1:8000/install.sh | sh
```

(The `install.sh` hard-codes `install.hosaka.xyz` for the public flow —
if you want this to work against your local server, temporarily swap the
URL or add a `HOSAKA_INSTALL_BASE` override when you harden the script.)

## Security notes

- Anyone piping a remote script to `sh` is trusting your TLS + your
  registry. Serve `install.sh` only over HTTPS with HSTS, pin to
  Cloudflare, and sign releases by tag.
- The installer never asks for sudo unless `/usr/local/bin` isn't
  writable by the current user — it tells the user before doing so.
- The launcher never exposes `:8421` on anything other than `127.0.0.1`
  unless `HOSAKA_PORT`/`-p` is overridden explicitly.
