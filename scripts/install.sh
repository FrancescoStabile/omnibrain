#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════
# OmniBrain — Install Script
# ══════════════════════════════════════════════════════════════════════════
# Usage: curl -sSL https://get.omnibrain-ai.dev | bash
# Or:    bash scripts/install.sh
# ══════════════════════════════════════════════════════════════════════════

set -euo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() { echo -e "${CYAN}[OmniBrain]${NC} $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# ── Check prerequisites ──
info "Checking prerequisites..."

if ! command -v python3 &> /dev/null; then
    error "Python 3 not found. Install Python 3.11+ and try again."
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]); then
    error "Python $PYTHON_VERSION found, but 3.11+ is required."
fi

success "Python $PYTHON_VERSION"

# ── Create venv ──
INSTALL_DIR="${HOME}/.local/share/omnibrain"
VENV_DIR="${INSTALL_DIR}/venv"

info "Creating virtual environment at ${VENV_DIR}..."
mkdir -p "$INSTALL_DIR"
python3 -m venv "$VENV_DIR"
source "${VENV_DIR}/bin/activate"

# ── Install OmniBrain ──
info "Installing OmniBrain..."
pip install --upgrade pip > /dev/null 2>&1
pip install omnibrain-ai > /dev/null 2>&1 || {
    # Fallback: install from local source if available
    if [ -f "pyproject.toml" ]; then
        info "Installing from local source..."
        pip install -e "." > /dev/null 2>&1
    else
        error "Failed to install OmniBrain. Try: pip install -e ."
    fi
}

# ── Create symlink ──
mkdir -p "${HOME}/.local/bin"
ln -sf "${VENV_DIR}/bin/omnibrain" "${HOME}/.local/bin/omnibrain"

# ── Install systemd service ──
if command -v systemctl &> /dev/null; then
    info "Installing systemd service..."
    SYSTEMD_DIR="${HOME}/.config/systemd/user"
    mkdir -p "$SYSTEMD_DIR"

    cat > "${SYSTEMD_DIR}/omnibrain.service" << 'EOF'
[Unit]
Description=OmniBrain — The AI that never sleeps
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=%h/.local/bin/omnibrain start
Restart=on-failure
RestartSec=10
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-%h/.omnibrain/.env

[Install]
WantedBy=default.target
EOF

    systemctl --user daemon-reload
    success "systemd service installed"
    info "Enable with: systemctl --user enable --now omnibrain"
fi

# ── Create data directory ──
DATA_DIR="${HOME}/.omnibrain"
mkdir -p "$DATA_DIR"

# Copy .env.example if no .env exists
if [ ! -f "${DATA_DIR}/.env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example "${DATA_DIR}/.env"
        info "Copied .env.example → ${DATA_DIR}/.env"
    fi
fi

# ── Verify installation ──
info "Verifying installation..."
if "${VENV_DIR}/bin/omnibrain" --version > /dev/null 2>&1; then
    VERSION=$("${VENV_DIR}/bin/omnibrain" --version 2>/dev/null || echo "unknown")
    success "OmniBrain ${VERSION} verified"
elif "${VENV_DIR}/bin/python" -c "import omnibrain" 2>/dev/null; then
    success "OmniBrain package verified"
else
    warn "Could not verify installation — try running 'omnibrain --version' manually"
fi

# ── Done ──
echo ""
success "OmniBrain installed!"
echo ""
info "Next steps:"
echo "  1. Run setup wizard:     omnibrain setup"
echo "  2. Start daemon:         omnibrain start"
echo "  3. Or as a service:      systemctl --user enable --now omnibrain"
echo ""
info "Data directory: ~/.omnibrain/"
echo ""
