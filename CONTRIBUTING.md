# Contributing

Thanks for helping make the iBUYPOWER AW5 / AW5D usable on Linux!

## Reporting a new cooler variant

Only PID `0x0407` ("CoolerMaster") is confirmed so far. If you have a
`0x0405` / `0x0406` ("Levelplay") or any other AW5-family unit, please open a
**New device variant** issue with:

- your `lsusb` line (the `xxxx:xxxx` ID),
- whether `python3 aw5d_lcd.py --list` detects it,
- whether the gauge lights up with the correct temperature when you run it.

Most variants almost certainly speak the same `report 0x10`; confirming lets us
widen the supported PID list.

## Dev notes

- The driver is a **single, dependency-free file** (`aw5d_lcd.py`, Python 3 standard
  library only). Please keep it that way — no `pip` requirements.
- Protocol details and how it was reverse-engineered live in
  [`RESEARCH.md`](RESEARCH.md).
- Test without a device: `python3 aw5d_lcd.py --dry-run --verbose`.
- Before opening a PR: `python3 -m py_compile aw5d_lcd.py` (and `ruff check` /
  `flake8` if you have them). CI runs these on every PR.

## Clean-room rule (please read)

This project ships **no vendor code** — no decompiled sources, firmware, or
bundled binaries. Everything here comes from our own *observation* of how the
hardware behaves, for **interoperability** (the same posture as the sibling
deepcool / thermalright / lian-li Linux projects). Please don't paste vendor
source or firmware into issues or PRs.

## Scope

The stock firmware gauge is implemented. The custom-image / GIF "ScreenTime"
mode is out of scope for now, but a clean-room PR for it is welcome.
