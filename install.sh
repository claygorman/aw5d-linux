#!/usr/bin/env bash
#
# Installer for aw5d-lcd — drives the iBUYPOWER AW5D cooler LCD on Linux.
#
# Installs:
#   * the driver           -> ~/.local/share/aw5d-lcd/aw5d_lcd.py
#   * a udev rule          -> /etc/udev/rules.d/99-aw5d-lcd.rules   (needs sudo)
#   * a systemd user unit  -> ~/.config/systemd/user/aw5d-lcd.service
# then enables + starts the service and turns on lingering so the screen keeps
# updating even with no active login session (or after a crash to the desktop).
#
# Usage:  ./install.sh          (install + start)
#         ./install.sh --uninstall
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARE_DIR="$HOME/.local/share/aw5d-lcd"
UNIT_DIR="$HOME/.config/systemd/user"
UDEV_RULE="/etc/udev/rules.d/99-aw5d-lcd.rules"
SERVICE="aw5d-lcd.service"

log() { printf '\033[1;36m[aw5d-lcd]\033[0m %s\n' "$*"; }

uninstall() {
    log "stopping + disabling service"
    systemctl --user disable --now "$SERVICE" 2>/dev/null || true
    rm -f "$UNIT_DIR/$SERVICE"
    systemctl --user daemon-reload 2>/dev/null || true
    rm -rf "$SHARE_DIR"
    if [[ -f "$UDEV_RULE" ]]; then
        log "removing udev rule (sudo)"
        sudo rm -f "$UDEV_RULE"
        sudo udevadm control --reload-rules || true
    fi
    log "uninstalled. (linger left enabled; disable with: loginctl disable-linger $USER)"
}

install() {
    command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }

    log "installing driver -> $SHARE_DIR"
    mkdir -p "$SHARE_DIR" "$UNIT_DIR"
    install -m 0755 "$REPO_DIR/aw5d_lcd.py" "$SHARE_DIR/aw5d_lcd.py"

    # Default config (update interval etc.) — never clobber an existing one.
    mkdir -p "$HOME/.config"
    if [[ ! -f "$HOME/.config/aw5d-lcd.env" ]]; then
        install -m 0644 "$REPO_DIR/aw5d-lcd.env.example" "$HOME/.config/aw5d-lcd.env"
        log "wrote default config -> ~/.config/aw5d-lcd.env (set AW5D_INTERVAL to change update rate)"
    fi

    log "installing udev rule -> $UDEV_RULE (sudo)"
    sudo install -m 0644 "$REPO_DIR/udev/99-aw5d-lcd.rules" "$UDEV_RULE"
    sudo udevadm control --reload-rules
    sudo udevadm trigger --subsystem-match=hidraw 2>/dev/null || true

    log "installing systemd user unit -> $UNIT_DIR/$SERVICE"
    install -m 0644 "$REPO_DIR/systemd/$SERVICE" "$UNIT_DIR/$SERVICE"
    systemctl --user daemon-reload
    systemctl --user enable --now "$SERVICE"

    log "enabling linger (service runs without an active login)"
    loginctl enable-linger "$USER" || log "could not enable linger (non-fatal)"

    sleep 1
    if systemctl --user is-active --quiet "$SERVICE"; then
        log "running. the cooler LCD should now show live CPU stats."
        log "no auto-update: re-run the installer (or 'just update') whenever you want the latest."
    else
        log "service is not active — check: journalctl --user -u $SERVICE -n 30"
        exit 1
    fi
}

case "${1:-}" in
    --uninstall|-u) uninstall ;;
    "" ) install ;;
    * ) echo "usage: $0 [--uninstall]" >&2; exit 2 ;;
esac
