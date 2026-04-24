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

`install.hosaka.xyz` is served by a Vercel project connected to this
GitHub repo. `vercel.json` in this directory handles all routing; no
build step is required.

### How it works

```
GitHub (main branch) -- push --> Vercel project (Root Directory: install)
                                       |
                                  vercel.json rewrites
                                       /          -> install.sh
                                       /windows   -> install.ps1
                                       /bin/*     -> bin/<name>
                                       /healthz   -> healthz.txt
                                       /version   -> VERSION
                                       |
                         GoDaddy DNS: install.hosaka.xyz
                           CNAME -> <project>.vercel-dns-017.com
```

### Deploying a change

Just push to `main`. Vercel auto-deploys whenever any file inside
`install/` changes. Pushes that only touch other parts of the repo
(`hosaka/`, `tests/`, etc.) are skipped automatically by the Ignored
Build Step filter. No CLI needed.

### First-time project setup (if recreating from scratch)

1. Create a new Vercel project connected to this repo.
2. Set **Root Directory** to `install` (not `./install`, not `/`).
3. Leave Framework Preset as **Other** and Build Command blank.
4. Set **Ignored Build Step** to:
   ```
   git diff HEAD^ HEAD --quiet -- install/
   ```
   This tells Vercel to skip the build when nothing under `install/`
   changed (exit 0 = skip, exit 1 = build — the opposite of intuition).
5. Add the custom domain `install.hosaka.xyz` in Project Settings.
6. In GoDaddy DNS, add a CNAME: `install` → the target Vercel gives you
   during domain setup (e.g. `cname.vercel-dns.com`).

### Smoke testing after a push

```powershell
# healthcheck
iwr https://install.hosaka.xyz/healthz -UseBasicParsing | Select-Object -ExpandProperty Content

# version
iwr https://install.hosaka.xyz/version -UseBasicParsing | Select-Object -ExpandProperty Content

# first line of windows installer (check it updated)
(iwr https://install.hosaka.xyz/windows -UseBasicParsing).Content.Split("`n")[0]

# first line of posix launcher
(iwr https://install.hosaka.xyz/bin/hosaka -UseBasicParsing).Content.Split("`n")[0]
```

Or with curl on mac/linux:

```bash
curl -fsSL https://install.hosaka.xyz/healthz
curl -fsSL https://install.hosaka.xyz/version
curl -fsSL https://install.hosaka.xyz/windows | head -3
curl -fsSL https://install.hosaka.xyz/bin/hosaka | head -3
```

## Image registry

The launcher pulls `ghcr.io/barkbarkbarkbarkbarkbarkbark/hosaka:latest`
by default. CI builds and pushes the image on every push to `main`
(multi-arch: `linux/amd64` + `linux/arm64`) and stamps the git commit
SHA as `HOSAKA_COMMIT` so `/api/health` always reports the exact
build in the running container.

```yaml
# .github/workflows/image.yml  (abbreviated)
- uses: docker/build-push-action@v6
  with:
    context: .
    file: docker/Dockerfile
    platforms: linux/amd64,linux/arm64
    push: true
    build-args: HOSAKA_COMMIT=${{ github.sha }}
    tags: |
      ghcr.io/barkbarkbarkbarkbarkbarkbark/hosaka:latest
      ghcr.io/barkbarkbarkbarkbarkbarkbark/hosaka:${{ github.ref_name }}
```

Make the package public from the GitHub UI (Packages → hosaka →
Settings → Change visibility → Public) so anonymous `docker pull`
works.

### Verifying the deployed commit

```powershell
iwr http://127.0.0.1:8421/api/health -UseBasicParsing | ConvertFrom-Json | Select commit, ui_built
```

Both `commit` (git SHA) and `ui_built: true` should be present after
`hosaka update && hosaka up`.

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
  registry. Serve `install.sh` only over HTTPS with HSTS (already set
  in `vercel.json`) and sign releases by tag.
- The installer never asks for sudo unless `/usr/local/bin` isn't
  writable by the current user — it tells the user before doing so.
- The launcher never exposes `:8421` on anything other than `127.0.0.1`
  unless `HOSAKA_PORT`/`-p` is overridden explicitly.
