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

# ── Node 24 + OpenClaw AI agent gateway ──────────────────────────────────────
# OpenClaw runs as a background gateway process alongside Hosaka.
# It gives the 'chat' command a full agent runtime: exec, fs, web_search,
# browser, image tools — powered by the configured OpenAI model.
RUN curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g openclaw@latest \
    && rm -rf /var/lib/apt/lists/*

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
