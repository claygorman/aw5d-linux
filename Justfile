# aw5d-lcd recipes. On Bazzite / SteamOS `just` is preinstalled; elsewhere: see https://just.systems
# Run `just` (or `just --list`) to see these.

# List recipes
default:
    @just --list

# Install the driver + user service + udev rule (see install.sh)
install:
    ./install.sh

# Remove everything installed
uninstall:
    ./install.sh --uninstall

# Manually update to the latest (this project never auto-updates)
update:
    git pull --ff-only
    ./install.sh
    systemctl --user restart aw5d-lcd
    @echo "aw5d-lcd updated + restarted. Nothing auto-updates — run 'just update' whenever you like."

# Show the service status
status:
    systemctl --user status aw5d-lcd

# Follow the live logs
logs:
    journalctl --user -u aw5d-lcd -f

# Show the detected device + sensors without installing
list:
    python3 aw5d_lcd.py --list

# Diagnose a dark screen (device / permissions / sensors / service)
doctor:
    python3 aw5d_lcd.py doctor

# Run the unit tests (stdlib unittest — no pip needed)
test:
    python3 -m unittest discover -s tests -v

# Set the LCD update interval in seconds, e.g. `just set-interval 2`
# (panel is ~1 Hz; 1s is ideal, 2-5s is fine, <0.5s just wastes traffic)
set-interval seconds:
    #!/usr/bin/env bash
    set -euo pipefail
    f=~/.config/aw5d-lcd.env
    mkdir -p ~/.config; touch "$f"
    # Replace the AW5D_INTERVAL line in place (or append) — don't clobber other settings.
    if grep -q '^AW5D_INTERVAL=' "$f"; then
        sed -i 's/^AW5D_INTERVAL=.*/AW5D_INTERVAL={{seconds}}/' "$f"
    else
        echo 'AW5D_INTERVAL={{seconds}}' >> "$f"
    fi
    systemctl --user restart aw5d-lcd
    echo "aw5d-lcd interval set to {{seconds}}s"
