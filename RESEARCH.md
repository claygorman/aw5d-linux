# iBUYPOWER AW5 / AW5D cooler LCD — Linux reverse-engineering notes

Goal: drive the round LCD on the **iBUYPOWER AW5 360mm AIO** (a.k.a. "AW5D") from Linux
(no vendor Windows software). There is currently **no** Linux support for this cooler in
liquidctl, CoolerControl, or any community project.

> **Legal / clean-room note.** These are our own *observations* of how the hardware behaves,
> for **interoperability**. We do **not** redistribute HYTE's / iBUYPOWER's proprietary code,
> decompiled source, or their bundled executables. Any driver we publish is written from
> scratch. Same posture as the lian-li-linux / deepcool-display-linux / thermalright-trcc-linux
> projects.

## Hardware

| Item | Value |
|---|---|
| Cooler | iBUYPOWER AW5 360mm RGB Liquid Cooler ("AW5 360MM RGB LIQUID COOLER") |
| USB device (LCD/controller) | **VID `0x3402` (13314) / PID `0x0407` (1031)** |
| Related PIDs (variants) | `0x0405`/`0x0406`/`0x0407` (1029/1030/1031) |
| USB class | HID, 1 interface, 2 **interrupt** endpoints (IN `0x81`, OUT `0x01`), 64 bytes, bInterval 10 — **no bulk endpoint** |
| Display data channel | HID **report ID `0x10`** (63-byte payload + 1 report-ID byte = one 64-byte packet) |
| Display MCU | **STM32** (DFU mode = `VID 0x3402 / PID 0x0A00`, flashed via STM32CubeProgrammer); display fw `K2862_...` |
| Screen | round LCD, refreshes at ~**1 Hz** (1 frame/sec, user-configurable) |
| RGB ring | separate ARGB on the motherboard header (ASUS Aura → OpenRGB), independent of the LCD |

On Linux the device binds to `hid-generic` at `/dev/hidrawN` and is **world-writable**, so a
userspace daemon can drive it with plain `write()` (64-byte buffers `[0x10, ...]`) — no libusb,
no bulk transfers.

## How the vendor software drives it (Windows)

1. **HYTE Nexus** (the Windows app) does **not** talk to the LCD itself. Its .NET service
   (`HYTE.Nexus.Service.dll` → `LightDancing.dll`, `Aw5dController` / `Aw5dAppManager`) just
   `Process.Start`s a bundled per-vendor helper **elevated, with no arguments**.
2. Vendor is chosen by PID: **`1030 → "Levelplay"`, `1031 → "CoolerMaster"`**. Our unit (1031)
   uses `resources/Aw5d/CoolerMaster/iBUYPOWER_AW5_v1.0.exe`.
3. That helper is a **small native Rust program** (`src/main.rs` + `src/device.rs`) using the
   **`hidapi` crate v2.6.3** — which is cross-platform, so the Linux port is a near-direct mirror.
   It is fully self-contained (reads sensors + renders + sends; Nexus feeds it nothing).
4. **Sensors**: read via **HWiNFO** (embedded `HWiNFO64.DLL`, `HWi32_*` shared-memory API) —
   cpu temperature, cpu usage, avg cpu MHz, gpu temp, gpu usage, memory usage.
5. **Screen**: opens the HID device (by product-name filter) and — for the **stock gauge** —
   simply writes **one 64-byte HID output report (`report 0x10`)** with the live CPU stats, ~1/sec.
   **There is NO separate wake / init / firmware-handshake packet** — confirmed by a fresh-spawn
   Frida capture of the whole connect sequence (see *Connect sequence* below). The helper's
   `Device connected. Checking firmware version…` log line is just standard **hidapi enumeration**
   (the `IOCTL 0x40000000` / `0x00020106` device-info + string-descriptor queries the OS answers
   automatically when you open a HID device by path — nothing app-specific is sent). The **JPEG**
   streaming path (`hid_write` 63-byte chunks + `hid_send_feature_report`, "sent X of Y bytes")
   is used **only** for the custom-image / GIF "ScreenTime" mode, not the default gauge.

## Linux port plan

```
open /dev/hidrawN for 0x3402/0x0407     (no handshake — confirmed)
   →  each ~1s:  build one 64-byte report 0x10 from lm-sensors  →  write()
sensors from lm-sensors (k10temp Tctl, /proc/stat, cpufreq) instead of HWiNFO
```

For the **stock gauge** there is nothing left to reverse — no image, no handshake, no framing
beyond the single 13-meaningful-byte `report 0x10` (validated field-by-field below). Everything
is reproducible on Linux today: we read the same sensors natively and hidraw `write()` is the
same call the Windows helper makes. (JPEG chunking is only needed if we later add custom-image
mode.)

## Connect sequence (fresh-spawn Frida capture — the "handshake")

Captured by spawning the CoolerMaster helper under Frida and hooking `CreateFileW`,
`Nt{Write,Read,DeviceIoControl}File`, and `HidD_*` from the very first instruction. Every ~2 s
cycle, the **entire** interaction with the LCD (`\\?\HID#VID_3402&PID_0407#…`) is:

```
OPEN   \\?\HID#VID_3402&PID_0407#…          open the device by path
IOCTL  40000000                              hidapi get-collection-info (OS-answered)
W      1008 08 0e a93b 000000 08 05 02 f0    ← the ONLY payload: one 64-byte report 0x10
R      0000…00 (64 bytes)                    read-back input report = all zeros (ignored)
IOCTL  06010200  ×5                          hidapi string-descriptor reads (OS-answered)
```

**There is no feature report, no version exchange, no wake command** — the `IOCTL`s are generic
hidapi device-info/string queries the OS fulfils, not app data. The helper even re-opens the
device every cycle (our driver can just hold it open). **So the complete protocol to light the
stock gauge is: open the HID device and `write()` one 64-byte `report 0x10`, repeat ~1/sec.**

## Protocol — stock gauge (report 0x10, validated against live HWiNFO readings)

The **stock "digital gauge" theme is rendered and animated by the device firmware** (the
spinning fan, arcs, layout). The helper just sends a **HID output report `0x10`** (~1/sec) with
the live CPU stats.

```
HID output report, report id 0x10, 64 bytes (bytes 13-63 = 0x00):
 offset:  0     1     2      3       4       5     6 7 8   9     10     11      12
 value:   0x10  0x08  USAGE  MHz_HI  MHz_LO  TEMP  0 0 0   arc   clkbar loadbar 0xF0/0xF9
```

> **Decode corrected 2026-07-06 using the on-screen photo** (`pictures/…5526-y.jpg`, which
> reads **"9%  3963 MHz"** — a *precise* clock). The earlier "bytes 4–5 = temp×256 little-endian"
> was wrong: **byte 4 is the MHz low byte**, not a temp fraction. It only *looked* right because
> `0x3bA9/256 = 59.66 ≈ 59`. The screen shows an **integer** temperature = **byte 5** alone.

Confirmed by capturing packets **with the helper's concurrent HWiNFO console output** as
ground truth (7800X3D, idle ~8 % / ~3.7 GHz / ~48–59 °C):

| packet bytes (b2 b3 b4 b5) | MHz = `b3<<8\|b4` | HWiNFO mhz | °C = `b5` | HWiNFO temp | usage=`b2` |
|---|---|---|---|---|---|
| `08 0e a9 3b` | `0x0EA9` = **3753** | 3753.4 | `0x3b` = **59** | 59.49 | 8 (8.02) |
| `08 0e e2 34` | `0x0EE2` = **3810** | 3810.5 | `0x34` = **52** | 52.05 | 8 (8.03) |
| `07 0e 71 30` | `0x0E71` = **3697** | 3697.3 | `0x30` = **48** | 48.09 | 7 (7.99) |

- **byte 0** = `0x10` report ID · **byte 1** = `0x08` constant (packet type).
- **byte 2 = `floor(cpu_usage %)`** (0–100). ✅ exact. Also drives the fan-spin animation speed.
- **bytes 3–4 = `avg_cpu_mhz` as a big-endian uint16** (`byte3 = mhz>>8`, `byte4 = mhz&0xff`).
  ✅ **exact, full precision** — this is the "3963 MHz" the screen prints (the orange bottom-right
  bar is a coarse level of the same clock, see byte 10).
- **byte 5 = `cpu_temp` in whole °C** (integer; the big number). ✅ exact. No fractional-temp byte
  exists (bytes 6–8 = `00`).
- **byte 9** = top **blue arc** level, tracks temp (≈`floor(temp/7)` near steady state; the
  firmware *eases/animates* it so it lags fast ramps — cosmetic).
- **byte 10** = bottom-right **orange (clock) bar** level, `0x05` idle → `0x07` load — cosmetic.
- **byte 11** = bottom-left **green (usage) bar** level, `0x02` idle → `0x0c` full — cosmetic.
- **byte 12** = `0xF0` normal → `0xF9` under high load — a flag/marker.
- **memory/GPU usage are read by the app but are NOT in this packet** — the stock gauge is
  100 % CPU (matches the on-screen photo: temp / usage % / MHz, all CPU).

Loaded samples (earlier staged CPU sweep — now re-decoded correctly, for the high end):
```
10 08 0f 0f 27 40 …09 05 04 f0   usage 15%, mhz 0x0f27=3879, temp 0x40=64C
10 08 31 10 d9 41 …0a 07 08 f0   usage 49%, mhz 0x10d9=4313, temp 0x41=65C
10 08 63 10 f8 53 …0d 07 0c f9   usage 99%, mhz 0x10f8=4344, temp 0x53=83C
```

**Linux driver (stock gauge)** — no handshake, no image. Open hidraw for `0x3402:0x0407` and
~1/sec `write()` a 64-byte report built from lm-sensors:
```
[0x10, 0x08,
 min(100, floor(cpu_usage)),     # byte2  usage %
 (round(avg_mhz) >> 8) & 0xff,   # byte3  MHz high byte
 round(avg_mhz) & 0xff,          # byte4  MHz low byte   (bytes3-4 = exact MHz, big-endian)
 round(cpu_temp) & 0xff,         # byte5  temp °C (integer)
 0, 0, 0,
 floor(cpu_temp/7),              # byte9  blue arc  (cosmetic, best-fit)
 0x05,                           # byte10 orange clock bar (cosmetic; 0x07 under load)
 min(0x0c, 2+floor(cpu_usage/12)),# byte11 green usage bar (cosmetic, best-fit)
 0xf0]                           # byte12 flag (→0xf9 when hot/busy, optional)
+ [0x00]*51
```
The three real readouts — **temp °C (byte5), usage % (byte2), MHz (bytes3–4)** — are exact;
bytes 9/10/11/12 are cosmetic gauge levels/flags with best-fit formulas (the firmware eases
them, so exact-match isn't needed).

## Status

- [x] Identify the device + transport (HID, report 0x10, no bulk)
- [x] Confirm no existing Linux driver
- [x] Trace the Windows driver chain → the CoolerMaster Rust helper
- [x] Determine it's `hidapi` + `HWiNFO` + report-0x10, ~1 Hz (JPEG path is custom-image only)
- [x] **Capture the connect sequence** — fresh-spawn Frida hook: **no handshake/wake/feature
  report**; the whole protocol is open + one `write()` of report 0x10, repeat ~1/sec
- [x] **Validate every packet byte** against the helper's concurrent HWiNFO output (usage=b2,
  mhz/256=b3, temp×256=b4-5 all exact; arc/bar/flag bytes are cosmetic best-fit)
- [ ] Write the Linux daemon (python-hidraw or Rust hidapi + lm-sensors) — **pure offline work,
  spec complete; no more Windows needed**
- [ ] Package + publish

## Prior art / templates (different vendors, same idea)

- `Blaster4385/deepcool-display-linux` — reads Linux CPU temp → pushes to a round LCD over HID
- `Lexonight1/thermalright-trcc-linux` — Thermalright LCD Control Center, Linux port
- `sgtaziz/lian-li-linux` — Lian Li LCD streaming (Rust + hidapi + ffmpeg)
