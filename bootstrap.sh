#!/usr/bin/env bash
#
# One-line installer for aw5d-lcd:
#
#   curl -fsSL https://raw.githubusercontent.com/claygorman/aw5d-linux/main/bootstrap.sh | bash
#
# Fetches the repo into ~/.local/share/aw5d-lcd-src and runs install.sh. No root
# for the driver itself (systemd --user + a udev rule installed via sudo); no
# reboot. Works on Bazzite / SteamOS / other atomic distros because $HOME is
# writable and the cooler's hidraw node is user-writable via the udev rule.
#
set -euo pipefail

REPO_URL="https://github.com/claygorman/aw5d-linux"
SRC_DIR="${AW5D_SRC_DIR:-$HOME/.local/share/aw5d-lcd-src}"

echo "[aw5d-lcd] installing from ${REPO_URL}"

if ! command -v git >/dev/null 2>&1; then
    echo "[aw5d-lcd] error: 'git' is required (it ships on Bazzite). Install it, or" >&2
    echo "           clone the repo manually and run ./install.sh" >&2
    exit 1
fi

if [ -d "${SRC_DIR}/.git" ]; then
    echo "[aw5d-lcd] updating existing checkout in ${SRC_DIR}"
    git -C "${SRC_DIR}" fetch --depth 1 -q origin main
    git -C "${SRC_DIR}" reset --hard -q origin/main
else
    rm -rf "${SRC_DIR}"
    git clone --depth 1 -q "${REPO_URL}" "${SRC_DIR}"
fi

exec bash "${SRC_DIR}/install.sh" "$@"
