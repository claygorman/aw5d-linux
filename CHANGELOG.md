# Changelog

All notable changes to this project are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Added
- Configurable update interval via `AW5D_INTERVAL` (env / `~/.config/aw5d-lcd.env`),
  in addition to the `--interval` flag; the service now reads the env file.
- `--version` flag.
- Warning + safe clamp when the interval is set below the panel's ~1 Hz refresh.
- `CONTRIBUTING.md`, a "new device variant" issue form, and `CODEOWNERS`.

## [1.0.0] - 2026-07-07

Initial public release.

### Added
- Native Linux driver (`aw5d_lcd.py`) for the iBUYPOWER AW5 / AW5D cooler LCD
  (USB HID `3402:0407`) — dependency-free, Python 3 standard library only.
- Stock CPU gauge over HID `report 0x10` (~1 Hz): usage, exact MHz, temperature —
  no vendor software, no handshake.
- systemd **user** service (linger-enabled), udev rule, and `install.sh`.
- Full reverse-engineering writeup and validated protocol in `RESEARCH.md`.
