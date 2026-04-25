# syntax=docker/dockerfile:1.6
# ─────────────────────────────────────────────────────────────────────────────
# Hosaka Field Terminal — Development & Shipping Dockerfile
#
# Build:   docker build -t hosaka -f docker/Dockerfile .
# Dev:     docker compose -f docker/compose.yml up
# Ship:    docker build -t hosaka:ship -f docker/Dockerfile .
# Export:  docker save hosaka:ship | gzip > hosaka-field-terminal.tar.gz
#
# Mirrors a headless Raspberry Pi: Debian Bookworm, Python 3.12,
# Hosaka in headless boot mode, web setup UI on port 8421.
# No systemd — the container IS the process supervisor.
# ─────────────────────────────────────────────────────────────────────────────

# ── stage 1: build the frontend SPA ──────────────────────────────────────────
FROM node:22-slim AS frontend-builder

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --prefer-offline

COPY frontend/ ./
RUN npm run build
# output lands in /build/hosaka/web/ui (vite.config.ts outDir)

FROM python:3.12-slim-bookworm AS base

# ── system packages (match a real Pi's toolset) ──────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        rsync \
        iproute2 \
        iputils-ping \
        procps \
        net-tools \
        bash \
        git \
        zstd \
        apt-transport-https \
        ca-certificates \
        gnupg \
    && curl -fsSL https://pkgs.tailscale.com/stable/debian/bookworm.noarmor.gpg | tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null \
    && curl -fsSL https://pkgs.tailscale.com/stable/debian/bookworm.tailscale-keyring.list | tee /etc/apt/sources.list.d/tailscale.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends tailscale \
    && rm -rf /var/lib/apt/lists/*

# ── Picoclaw agent binary ─────────────────────────────────────────────────────
# Picoclaw is a lightweight agentic framework. The gateway runs as a background
# process alongside Hosaka, giving the console a full agent runtime.
# Auto-detect arch: amd64 or arm64.
ARG PICOCLAW_VERSION=0.2.4
RUN ARCH=$(dpkg --print-architecture) \
    && case "$ARCH" in \
         amd64) PICOCLAW_ARCH="x86_64" ;; \
         arm64) PICOCLAW_ARCH="arm64"   ;; \
         *)     echo "Unsupported arch: $ARCH" && exit 1 ;; \
       esac \
    && curl -L "https://github.com/sipeed/picoclaw/releases/download/v${PICOCLAW_VERSION}/picoclaw_Linux_${PICOCLAW_ARCH}.tar.gz" \
         -o /tmp/picoclaw.tar.gz \
    && tar -xzf /tmp/picoclaw.tar.gz -C /tmp \
    && chmod +x /tmp/picoclaw \
    && mv /tmp/picoclaw /usr/local/bin/picoclaw \
    && rm /tmp/picoclaw.tar.gz \
    && picoclaw version

# ── application directory structure ──────────────────────────────────────────
# HOSAKA_COMMIT is stamped in at build time by CI (--build-arg HOSAKA_COMMIT=<sha>).
# Falls back to "dev" when building locally without passing the arg.
ARG HOSAKA_COMMIT=dev

ENV APP_ROOT=/opt/hosaka-field-terminal \
    HOSAKA_STATE_PATH=/var/lib/hosaka/state.json \
    HOSAKA_BOOT_MODE=headless \
    HOSAKA_WEB_HOST=0.0.0.0 \
    HOSAKA_WEB_PORT=8421 \
    PYTHONUNBUFFERED=1 \
    HOSAKA_COMMIT=${HOSAKA_COMMIT}

RUN mkdir -p /opt/hosaka-field-terminal /var/lib/hosaka /var/log/hosaka

RUN mkdir -p /root/.picoclaw

WORKDIR /opt/hosaka-field-terminal

# ── Python dependencies (cached layer — only busts when requirements change) ─
COPY requirements-hosaka.txt .
RUN python -m venv .venv \
    && .venv/bin/pip install --no-cache-dir --upgrade pip \
    && .venv/bin/pip install --no-cache-dir -r requirements-hosaka.txt

# ── copy application code ────────────────────────────────────────────────────
COPY hosaka/            hosaka/
COPY docs/              docs/
COPY identity/          identity/
COPY manager/           manager/
COPY skills/            skills/
COPY scripts/           scripts/
COPY systemd/           systemd/
COPY tests/             tests/
COPY README.md          .

# ── inject the pre-built frontend SPA ────────────────────────────────────────
COPY --from=frontend-builder /build/hosaka/web/ui hosaka/web/ui/

RUN chmod +x scripts/*.sh
RUN python scripts/bootstrap_picoclaw_runtime.py --home /root --seed-config

# ── expose the web setup / progress API ──────────────────────────────────────
EXPOSE 8421

# ── healthcheck ──────────────────────────────────────────────────────────────
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:8421/progress || exit 1

# ── default entrypoint ───────────────────────────────────────────────────────
ENTRYPOINT ["/opt/hosaka-field-terminal/.venv/bin/python", "-m", "hosaka"]
