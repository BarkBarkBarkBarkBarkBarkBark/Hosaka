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

Both install the Docker client launcher and download the container image
before reporting success. Docker must already be installed and running.
They do not install native appliance services or configure fullscreen boot.
The Unix installer refuses to replace a non-Docker Hosaka launcher; the
Windows installer refuses to shadow a different Hosaka installation.

Unix installs to `/usr/local/bin` by default (using sudo when needed).
If you override `HOSAKA_PREFIX` and its `bin` directory is not on PATH, the
installer prints the shell configuration change you need. Windows installs
to `%LOCALAPPDATA%\Hosaka\bin` and adds it to both the user PATH and the
current PowerShell session.

## What the user gets

| Command                       | Effect                                                         |
| ----------------------------- | -------------------------------------------------------------- |
| `hosaka up`                   | Start the local node (web UI on `http://127.0.0.1:8421`)       |
| `hosaka tui`                  | Run the native TUI inside the local container                 |
| `hosaka open`                 | Open the web UI in the browser                                 |
| `hosaka link <host[:port]>`   | Route browser/status at a remote Hosaka; native TUI needs SSH |
| `hosaka configure llm ...`   | Select a provider/model and privately prompt for its key       |
| `hosaka workspace PATH`      | Share a host folder read-only at `/workspace`                  |
| `hosaka workspace PATH --read-write` | Explicitly allow edits to the shared host folder     |
| `hosaka workspace clear`     | Use the private persistent writable workspace                 |
| `hosaka secrets <verb>`      | Manage persistent container credentials                       |
| `hosaka picoclaw <args>`     | Run PicoClaw inside the container                              |
| `hosaka unlink`               | Go back to the local node                                      |
| `hosaka update`               | Pull the latest image and recreate a running node when changed |
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

Both installers fetch the launcher file(s) from
`https://install.hosaka.xyz/bin/<name>` at install time. Re-run the
installer to refresh the launcher itself; `hosaka update` refreshes the
container image, not the installed CLI.

Stop a running node with `hosaka down` before changing workspace mounts.
Source installation is separate: use the repository-root
[`install.sh`](../install.sh), not this Docker installer. Provider setup,
workspace permission examples, and the isolation limits are documented in
the [main README](../README.md#set-up-a-model-and-api-key).

Downloads are staged and checked before installation. Image download
failures produce a nonzero exit instead of a misleading success message.
Set `HOSAKA_NO_PULL=1` to install just the launcher; `hosaka up` will still
need to obtain the image.

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
by default. CI builds the image on every push to `main`
(multi-arch: `linux/amd64` + `linux/arm64`) and stamps the git commit
SHA as `HOSAKA_COMMIT` so `/api/health` always reports the exact
build in the running container and frontend build stamp.

The workflow first runs the Unix and Windows installer regression tests,
then publishes a candidate image under `:build-<full-commit-sha>`. It runs
that exact image by digest and checks `/api/health` and `/build-stamp.json`
against the commit. Only after those checks pass does it promote the image
to `:latest`, `:main`, `:edge`, and the commit-specific tag. A failed build
or smoke test does not move the default download.

Tag pushes publish their version tag after verification; `:latest` currently
tracks verified `main` builds, not tagged releases.

```yaml
# .github/workflows/image.yml  (abbreviated)
- uses: docker/build-push-action@v6
  with:
    context: .
    file: docker/Dockerfile
    platforms: linux/amd64,linux/arm64
    push: true
    build-args: HOSAKA_COMMIT=${{ github.sha }}
    tags: ghcr.io/barkbarkbarkbarkbarkbarkbark/hosaka:build-${{ github.sha }}
# Smoke-test the returned image digest, then promote the verified digest.
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
bash tests/test_install.sh

# With PowerShell installed:
pwsh -NoProfile -File tests/test_install.ps1

# With an HTTP server already serving install/ on port 8000:
curl -fsSL http://127.0.0.1:8000/install.sh | \
  HOSAKA_INSTALL_BASE=http://127.0.0.1:8000 \
  HOSAKA_NO_PULL=1 HOSAKA_PREFIX="$HOME/.local" sh
```

`HOSAKA_INSTALL_BASE` overrides the download host on Unix and Windows.
Environment overrides must be passed to the installer shell, not just curl.
The tests use temporary installation directories and mocked downloads/Docker;
they do not replace your real launcher.

## Security notes

- Anyone piping a remote script to `sh` is trusting your TLS + your
  registry. Serve `install.sh` only over HTTPS with HSTS (already set
  in `vercel.json`) and sign releases by tag.
- The installer never asks for sudo unless `/usr/local/bin` isn't
  writable by the current user — it tells the user before doing so.
- The launcher never exposes `:8421` on anything other than `127.0.0.1`
  unless `HOSAKA_PORT`/`-p` is overridden explicitly.
