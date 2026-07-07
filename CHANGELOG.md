# Changelog

All notable changes to this project are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

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
