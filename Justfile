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

# Set the LCD update interval in seconds, e.g. `just set-interval 2`
# (panel is ~1 Hz; 1s is ideal, 2-5s is fine, <0.5s just wastes traffic)
set-interval seconds:
    echo 'AW5D_INTERVAL={{seconds}}' > ~/.config/aw5d-lcd.env
    systemctl --user restart aw5d-lcd
    @echo "aw5d-lcd interval set to {{seconds}}s"
