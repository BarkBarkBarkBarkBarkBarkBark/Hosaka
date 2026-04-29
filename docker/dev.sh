#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# dev.sh — One-command Hosaka development environment
#
# Usage:
#   ./docker/dev.sh              # build + start (headless, web UI on :8421)
#   ./docker/dev.sh build        # rebuild image from scratch
#   ./docker/dev.sh shell        # open a bash shell in the running container
#   ./docker/dev.sh tui          ★ full interactive TUI (your main dev loop)
#   ./docker/dev.sh test         # run the test suite inside the container
#   ./docker/dev.sh logs         # tail container logs
#   ./docker/dev.sh status       # show container + picoclaw gateway health
#   ./docker/dev.sh export       # export a shippable image tarball
#   ./docker/dev.sh stop         # stop everything
#   ./docker/dev.sh nuke         # stop + delete volumes (full reset)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/compose.yml"
PROJECT_NAME="hosaka"

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${CYAN}[hosaka-dev]${NC} $*"; }
ok()    { echo -e "${GREEN}[hosaka-dev]${NC} $*"; }
warn()  { echo -e "${YELLOW}[hosaka-dev]${NC} $*"; }

dc() {
  LOCAL_UID="$(id -u)" LOCAL_GID="$(id -g)" docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" "$@"
}

case "${1:-up}" in

  up)
    info "Starting Hosaka dev environment (headless)..."
    dc up -d --build --remove-orphans
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║                                                  ║${NC}"
    echo -e "${CYAN}║  ${GREEN}Hosaka dev environment is running${CYAN}              ║${NC}"
    echo -e "${CYAN}║                                                  ║${NC}"
    echo -e "${CYAN}║  ${NC}Web UI:     http://localhost:8421${CYAN}               ║${NC}"
    echo -e "${CYAN}║  ${NC}Picoclaw:   gateway on :18790 (inside container)${CYAN}║${NC}"
    echo -e "${CYAN}║                                                  ║${NC}"
    echo -e "${CYAN}║  ${NC}Frontend edits rebuild immediately in dev${CYAN}     ║${NC}"
    echo -e "${CYAN}║                                                  ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════╝${NC}"
    echo ""
    info "Next steps:"
    echo "  ./docker/dev.sh tui          ★ Full interactive TUI (your main dev loop)"
    echo "  ./docker/dev.sh shell        Bash shell in container"
    echo "  ./docker/dev.sh logs         Tail app + frontend watcher logs"
    echo "  ./docker/dev.sh test         Run test suite"
    echo ""
    ;;

  tui|console)
    info "Starting frontend watcher (for live SPA rebuilds)..."
    dc up -d frontend-watch
    info "Stopping headless service (if running)..."
    dc stop hosaka 2>/dev/null || true
    echo ""
    info "Starting Hosaka interactive TUI (console mode)..."
    info "This is the same experience as booting a real Pi."
    info "Ctrl-C to exit back to your host shell."
    echo ""
    dc run --rm --service-ports --remove-orphans --build console
    ;;

  build)
    info "Rebuilding Hosaka image from scratch..."
    dc build --no-cache
    ok "Build complete."
    ;;

  shell)
    if dc ps --status running | grep -q hosaka-dev; then
      info "Opening shell in running hosaka-dev container..."
      dc exec hosaka bash
    else
      info "No running container — starting a disposable shell..."
      dc run --rm --entrypoint bash console
    fi
    ;;

  test)
    info "Running test suite inside container..."
    if dc ps --status running | grep -q hosaka-dev; then
      dc exec hosaka \
        /opt/hosaka-field-terminal/.venv/bin/python -m pytest tests/ -v
    else
      dc run --rm --entrypoint /opt/hosaka-field-terminal/.venv/bin/python \
        console -m pytest tests/ -v
    fi
    ;;

  logs)
    dc logs -f hosaka frontend-watch
    ;;

  status)
    info "Container status:"
    dc ps
    echo ""
    info "Hosaka health:"
    curl -sf http://localhost:8421/progress 2>/dev/null | python3 -m json.tool 2>/dev/null \
      || warn "Hosaka web UI not responding on :8421"
    echo ""
    info "Picoclaw gateway health:"
    curl -sf http://localhost:18790/health 2>/dev/null | python3 -m json.tool 2>/dev/null \
      || warn "Picoclaw gateway not responding on :18790"
    ;;

  export)
    IMAGE_TAG="${2:-hosaka:ship}"
    OUTFILE="${3:-hosaka-field-terminal.tar.gz}"
    info "Building shippable image as ${IMAGE_TAG}..."
    docker build -t "$IMAGE_TAG" -f "$SCRIPT_DIR/Dockerfile" "$REPO_ROOT"
    info "Exporting to ${OUTFILE}..."
    docker save "$IMAGE_TAG" | gzip > "$OUTFILE"
    SIZE=$(du -h "$OUTFILE" | cut -f1)
    echo ""
    ok "Exported: ${OUTFILE} (${SIZE})"
    echo ""
    echo "  Ship to any Docker-capable device (Pi, server, VM):"
    echo ""
    echo "    scp ${OUTFILE} pi@<device-ip>:~/"
    echo "    ssh pi@<device-ip>"
    echo "    docker load < ${OUTFILE}"
    echo "    docker run -d -p 8421:8421 --name hosaka ${IMAGE_TAG}"
    echo ""
    ;;

  stop)
    info "Stopping Hosaka dev environment..."
    dc down
    ok "Stopped."
    ;;

  nuke)
    warn "Stopping and removing all containers, volumes, and state..."
    dc down -v
    ok "Clean slate. Run ./docker/dev.sh to start fresh."
    ;;

  *)
    echo "Hosaka dev environment"
    echo ""
    echo "Usage: ./docker/dev.sh <command>"
    echo ""
    echo "Commands:"
    echo "  up           Start headless background (default)"
    echo "  tui          ★ Full interactive TUI — your main dev loop"
    echo "  build        Rebuild image from scratch"
    echo "  shell        Bash shell in the Hosaka container"
    echo "  console      Alias for tui"
    echo "  test         Run the test suite"
    echo "  logs         Tail container logs"
    echo "  status       Show container + picoclaw gateway health"
    echo "  export       Build and save a shippable image tarball"
    echo "  stop         Stop all containers"
    echo "  nuke         Stop + delete all volumes (full reset)"
    echo ""
    exit 1
    ;;
esac
