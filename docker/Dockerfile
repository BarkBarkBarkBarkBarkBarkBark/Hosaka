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
ENV APP_ROOT=/opt/hosaka-field-terminal \
    HOSAKA_STATE_PATH=/var/lib/hosaka/state.json \
    HOSAKA_BOOT_MODE=headless \
    HOSAKA_WEB_HOST=0.0.0.0 \
    HOSAKA_WEB_PORT=8421 \
    PYTHONUNBUFFERED=1

RUN mkdir -p /opt/hosaka-field-terminal /var/lib/hosaka

WORKDIR /opt/hosaka-field-terminal

# ── Python dependencies (cached layer — only busts when requirements change) ─
COPY requirements-hosaka.txt .
RUN python -m venv .venv \
    && .venv/bin/pip install --no-cache-dir --upgrade pip \
    && .venv/bin/pip install --no-cache-dir -r requirements-hosaka.txt

# ── copy application code ────────────────────────────────────────────────────
COPY hosaka/            hosaka/
COPY docs/              docs/
COPY scripts/           scripts/
COPY systemd/           systemd/
COPY tests/             tests/
COPY README.md          .

RUN chmod +x scripts/*.sh

# ── expose the web setup / progress API ──────────────────────────────────────
EXPOSE 8421

# ── healthcheck ──────────────────────────────────────────────────────────────
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:8421/progress || exit 1

# ── default entrypoint ───────────────────────────────────────────────────────
ENTRYPOINT ["/opt/hosaka-field-terminal/.venv/bin/python", "-m", "hosaka"]
