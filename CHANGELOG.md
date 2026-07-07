# Changelog

All notable changes to this project are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Added
- `aw5d-lcd self-update` — a **manual** updater (fetches latest via git, reinstalls,
  restarts the service). Runs only when invoked; nothing auto-updates. `AW5D_SRC_DIR`
  overrides the checkout location.
- An **`aw5d-lcd`** command on `PATH` — the installer creates `~/.local/bin/aw5d-lcd`
  (override the dir with `AW5D_BIN_DIR`), so it's `aw5d-lcd doctor` instead of a long path.
- Installer **preflight**: detects a Python 3.8+ interpreter (`python3` or `python`), fails
  early with a clear message if missing, and renders the launcher + systemd unit with it
  (robust to non-standard Python locations).
- `doctor` now also reports the Python version and whether `aw5d-lcd` is on your `PATH`.
- Unit test suite (stdlib `unittest`, `tests/`) run in CI — asserts `build_packet`
  against the captured golden packet (byte-for-byte), plus MHz/temp encoding, usage
  math, and env parsing. Run with `just test`.
- `doctor` command (`python3 aw5d_lcd.py doctor` / `just doctor`) — diagnoses device
  presence, hidraw writability, CPU sensors, and service state, with fix hints; exits
  non-zero on a critical failure. The first stop for a dark screen.
- Commands `run` / `doctor` / `list` (positional) and a README **Usage** section.
- One-line install via `bootstrap.sh` (`curl … | bash`) — fetches the repo and runs
  `install.sh`; no reboot / no `rpm-ostree` layering needed on Bazzite/atomic.
- A `Justfile` (`just install` / `uninstall` / `update` / `doctor` / `status` / `logs` / `set-interval N`).
- "Updating" guide + `just update` for **manual** updates; documented that the project
  **never auto-updates** (no background updater/timer/cron; the driver makes no network calls).

## [1.0.0] - 2026-07-07

Initial public release.

### Added
- Native Linux driver (`aw5d_lcd.py`) for the iBUYPOWER AW5 / AW5D cooler LCD
  (USB HID `3402:0407`) — dependency-free, Python 3 standard library only.
- Stock CPU gauge over HID `report 0x10` (~1 Hz): usage, exact MHz, temperature —
  no vendor software, no handshake.
- Configurable update interval via `--interval` / `AW5D_INTERVAL`
  (`~/.config/aw5d-lcd.env`), with a warning + safe clamp when set too low.
- `--version` flag.
- systemd **user** service (linger-enabled), udev rule, and `install.sh`.
- CI (byte-compile + lint + shell syntax), `CONTRIBUTING.md`, a "new device
  variant" issue form, and `CODEOWNERS`.
- Full reverse-engineering writeup and validated protocol in `RESEARCH.md`.

[Unreleased]: https://github.com/claygorman/aw5d-linux/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/claygorman/aw5d-linux/releases/tag/v1.0.0
