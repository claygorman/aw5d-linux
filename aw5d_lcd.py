#!/usr/bin/env python3
"""
aw5d-lcd — drive the iBUYPOWER AW5D AIO cooler's round LCD from Linux.

The AW5D liquid cooler (USB ``3402:0407``) exposes its round display as a plain
USB-HID device that binds to ``hid-generic`` at ``/dev/hidrawN``.  The stock
"digital gauge" theme (big temperature number, spinning fan, coloured arc/bars)
is drawn and *animated by the cooler's own firmware* — the host does not stream
an image for it.  All the host has to do is push **one 64-byte HID output report
(report id 0x10)** roughly once per second with the live CPU stats:

    offset  0     1     2      3       4       5     6 7 8   9    10      11      12
    value   0x10  0x08  USAGE  MHz_HI  MHz_LO  TEMP  0 0 0   arc  clkbar  usebar  0xF0/F9

    byte 2      = CPU usage %                 (0-100)
    bytes 3-4   = average CPU clock in MHz     (big-endian uint16)   -> exact
    byte 5      = CPU temperature in °C        (integer)             -> exact
    byte 9      = top blue arc level    (cosmetic, tracks temperature)
    byte 10     = orange clock-bar level (cosmetic, tracks clock)
    byte 11     = green usage-bar level  (cosmetic, tracks usage)
    byte 12     = 0xF0 normal / 0xF9 under high load (styling flag)
    bytes 13-63 = 0x00 padding

There is **no handshake / wake / init packet** — open the hidraw node and write.
(Confirmed by capturing the vendor helper's full connect sequence: the only
device I/O is a single ``write()`` of this report, repeated ~1/sec.)

This is a clean-room reimplementation from observed hardware behaviour, written
for interoperability.  It ships no vendor code.  See RESEARCH.md.

Authored by Anthropic's Claude (Claude Code) working with Clay Gorman, who owns
the hardware, reverse-engineered the protocol, and tested it on the real device.
See the "Authorship & AI disclosure" section of the README.

Requires only the Python 3 standard library.  Reads sensors from sysfs
(``k10temp`` for CPU temperature, ``/proc/stat`` for usage, ``cpufreq`` for
clock) so it needs no external tools.  The hidraw node must be writable by the
running user (see udev/99-aw5d-lcd.rules).
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import shutil
import signal
import sys
import time

VENDOR_ID = 0x3402
PRODUCT_ID = 0x0407

REPORT_ID = 0x10
REPORT_LEN = 64  # report id + 63 payload bytes

__version__ = "1.0.0"

# The cooler's firmware re-renders the gauge at ~1 Hz, so ~1s is the natural cadence.
DEFAULT_INTERVAL = 1.0
MIN_USEFUL_INTERVAL = 0.5  # below this, pushing adds USB/CPU traffic with no visible gain
MIN_INTERVAL = 0.05        # hard floor to avoid a busy loop

# --------------------------------------------------------------------------- #
# Device discovery
# --------------------------------------------------------------------------- #

_HID_ID_RE = re.compile(r"HID_ID=[0-9A-Fa-f]+:0*([0-9A-Fa-f]+):0*([0-9A-Fa-f]+)")


def find_hidraw(vid: int = VENDOR_ID, pid: int = PRODUCT_ID) -> str | None:
    """Return ``/dev/hidrawN`` for the first HID node matching *vid*:*pid*."""
    for path in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        uevent = os.path.join(path, "device", "uevent")
        try:
            with open(uevent) as fh:
                data = fh.read()
        except OSError:
            continue
        m = _HID_ID_RE.search(data)
        if m and int(m.group(1), 16) == vid and int(m.group(2), 16) == pid:
            return "/dev/" + os.path.basename(path)
    return None


# --------------------------------------------------------------------------- #
# Sensors (sysfs only — no external binaries)
# --------------------------------------------------------------------------- #

# hwmon driver names that expose the CPU package/Tctl temperature, in order of
# preference for an AMD Ryzen box (this cooler ships on AMD builds).
_CPU_HWMON_NAMES = ("k10temp", "zenpower", "coretemp")
# label substrings that identify the "whole CPU" temperature within that chip
_CPU_TEMP_LABELS = ("tctl", "tdie", "package", "cpu")


def find_cpu_temp_input() -> str | None:
    """Locate the sysfs ``tempN_input`` for the CPU package temperature."""
    for name_pref in _CPU_HWMON_NAMES:
        for hw in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
            try:
                with open(os.path.join(hw, "name")) as fh:
                    if fh.read().strip() != name_pref:
                        continue
            except OSError:
                continue
            # Prefer an input whose label matches a "whole CPU" temperature.
            for label_path in sorted(glob.glob(os.path.join(hw, "temp*_label"))):
                try:
                    with open(label_path) as fh:
                        label = fh.read().strip().lower()
                except OSError:
                    continue
                if any(key in label for key in _CPU_TEMP_LABELS):
                    inp = label_path.replace("_label", "_input")
                    if os.path.exists(inp):
                        return inp
            # Fall back to temp1_input (Tctl on k10temp).
            inp = os.path.join(hw, "temp1_input")
            if os.path.exists(inp):
                return inp
    return None


def read_temp_c(path: str) -> float:
    with open(path) as fh:
        return int(fh.read().strip()) / 1000.0


def read_cpu_times() -> tuple[int, int]:
    """Return (total_jiffies, idle_jiffies) from the aggregate ``/proc/stat`` line."""
    with open("/proc/stat") as fh:
        fields = fh.readline().split()
    vals = [int(x) for x in fields[1:]]
    # user nice system idle iowait irq softirq steal guest guest_nice
    idle = vals[3] + (vals[4] if len(vals) > 4 else 0)  # idle + iowait
    return sum(vals), idle


def cpu_usage_pct(prev: tuple[int, int], now: tuple[int, int]) -> float:
    dtotal = now[0] - prev[0]
    didle = now[1] - prev[1]
    if dtotal <= 0:
        return 0.0
    return max(0.0, min(100.0, 100.0 * (dtotal - didle) / dtotal))


def read_avg_mhz() -> int:
    """Average current core clock across all CPUs, in MHz (0 if unavailable)."""
    freqs = []
    for f in glob.glob("/sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq"):
        try:
            with open(f) as fh:
                freqs.append(int(fh.read().strip()))
        except OSError:
            pass
    if not freqs:
        return 0
    return int(round(sum(freqs) / len(freqs) / 1000.0))  # kHz -> MHz


# --------------------------------------------------------------------------- #
# Packet
# --------------------------------------------------------------------------- #


def build_packet(usage: float, mhz: int, temp: float) -> bytes:
    """Build the 64-byte report-0x10 frame from live CPU stats.

    The three real readouts — usage% (byte2), MHz (bytes3-4, big-endian) and
    temperature °C (byte5) — are exact.  bytes 9/10/11/12 are cosmetic gauge
    levels/flags; the firmware eases them, so best-fit values look correct.
    """
    u = max(0, min(100, int(round(usage))))
    m = max(0, min(0xFFFF, int(round(mhz))))
    t = max(0, min(0xFF, int(round(temp))))

    arc = max(0, min(0x1F, t // 7))                 # byte9  blue temperature arc
    clk_bar = 0x07 if u >= 40 else 0x05             # byte10 orange clock bar
    use_bar = max(0x02, min(0x0C, 2 + u // 12))     # byte11 green usage bar
    flag = 0xF9 if (t >= 80 or u >= 90) else 0xF0   # byte12 high-load styling flag

    pkt = bytearray(REPORT_LEN)
    pkt[0] = REPORT_ID
    pkt[1] = 0x08
    pkt[2] = u
    pkt[3] = (m >> 8) & 0xFF
    pkt[4] = m & 0xFF
    pkt[5] = t
    # bytes 6-8 stay 0
    pkt[9] = arc
    pkt[10] = clk_bar
    pkt[11] = use_bar
    pkt[12] = flag
    return bytes(pkt)


# --------------------------------------------------------------------------- #
# Driver loop
# --------------------------------------------------------------------------- #


class Stop(Exception):
    pass


def _install_signal_handlers() -> None:
    def handler(signum, frame):
        raise Stop()

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


def open_device(path: str) -> int:
    return os.open(path, os.O_WRONLY)


def log(msg: str, *, verbose: bool = True) -> None:
    if verbose:
        print(f"[aw5d-lcd] {msg}", flush=True)


def run(args: argparse.Namespace) -> int:
    _install_signal_handlers()

    # Guard the update interval. The panel only refreshes ~1 Hz, so very small
    # intervals just burn USB/CPU for no visible benefit; 0 would busy-loop.
    if args.interval < MIN_INTERVAL:
        log(f"WARNING: interval {args.interval}s is too low; clamping to {MIN_INTERVAL}s "
            "(0 would busy-loop the CPU)", verbose=True)
        args.interval = MIN_INTERVAL
    elif args.interval < MIN_USEFUL_INTERVAL:
        log(f"NOTE: interval {args.interval}s is below the panel's ~1 Hz refresh — this adds "
            "USB/CPU traffic with no visible benefit. ~1s is ideal; 2-5s is fine and lighter.",
            verbose=True)

    temp_input = args.temp_input or find_cpu_temp_input()
    if not temp_input:
        log("WARNING: no CPU temperature sensor found (k10temp/zenpower/coretemp); "
            "temperature will read 0", verbose=True)

    def sample(prev_times):
        now_times = read_cpu_times()
        usage = cpu_usage_pct(prev_times, now_times)
        mhz = read_avg_mhz()
        temp = read_temp_c(temp_input) if temp_input else 0.0
        return now_times, usage, mhz, temp

    # Seed a first /proc/stat sample so usage is meaningful.
    prev_times = read_cpu_times()
    time.sleep(min(0.25, args.interval))

    fd = -1
    dev_path = args.device
    backoff = 1.0

    try:
        while True:
            prev_times, usage, mhz, temp = sample(prev_times)
            pkt = build_packet(usage, mhz, temp)

            if args.verbose or args.dry_run:
                log(
                    f"usage={usage:5.1f}%  mhz={mhz:5d}  temp={temp:5.1f}C  ->  "
                    + pkt[:13].hex(" "),
                    verbose=True,
                )

            if not args.dry_run:
                if fd < 0:
                    dev_path = args.device or find_hidraw()
                    if not dev_path:
                        log(f"device {VENDOR_ID:04x}:{PRODUCT_ID:04x} not found; "
                            f"retrying in {backoff:.0f}s")
                        time.sleep(backoff)
                        backoff = min(backoff * 2, 15.0)
                        continue
                    try:
                        fd = open_device(dev_path)
                        log(f"opened {dev_path}")
                        backoff = 1.0
                    except OSError as exc:
                        log(f"cannot open {dev_path}: {exc}; retrying in {backoff:.0f}s")
                        time.sleep(backoff)
                        backoff = min(backoff * 2, 15.0)
                        continue
                try:
                    os.write(fd, pkt)
                except OSError as exc:
                    log(f"write failed ({exc}); will reopen device")
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                    fd = -1
                    continue

            if args.once:
                break
            time.sleep(args.interval)
    except Stop:
        log("stopping")
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
    return 0


def _env_interval() -> float:
    """Frame interval default, overridable via the ``AW5D_INTERVAL`` env var."""
    raw = os.environ.get("AW5D_INTERVAL")
    if raw is None:
        return DEFAULT_INTERVAL
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_INTERVAL


def _check(label: str, state, detail: str = "", hint: str = "") -> bool:
    """Print one doctor line. state: True=OK, None=WARN, False=FAIL. Returns state is not False."""
    mark = {True: "OK  ", None: "WARN", False: "FAIL"}[state]
    print(f"[{mark}] {label}" + (f": {detail}" if detail else ""))
    if hint and state is not True:
        print(f"       -> {hint}")
    return state is not False


def doctor() -> int:
    """Run diagnostics and print a pass/fail report. Exit 1 if a critical check fails."""
    print("aw5d-lcd doctor\n")
    ok = True

    py = ".".join(str(n) for n in sys.version_info[:3])
    _check("python >= 3.8", True if sys.version_info >= (3, 8) else None,
           f"{py} on {sys.platform}",
           "the driver needs Python 3.8+ (uses bytes.hex separator); please upgrade")

    dev = find_hidraw()
    ok &= _check(f"cooler HID device {VENDOR_ID:04x}:{PRODUCT_ID:04x}", dev is not None,
                 dev or "NOT FOUND",
                 "is the cooler's USB header plugged in? check `lsusb | grep -i 3402`")

    if dev is not None:
        writable = os.access(dev, os.W_OK)
        ok &= _check(f"{dev} writable", writable, "yes" if writable else "PERMISSION DENIED",
                     f"install the udev rule (udev/99-aw5d-lcd.rules) or: sudo chmod 0666 {dev}")

    temp_input = find_cpu_temp_input()
    if temp_input:
        _check("CPU temperature sensor", True, f"{temp_input} = {read_temp_c(temp_input):.1f} C")
    else:
        _check("CPU temperature sensor", None, "not found",
               "no k10temp/zenpower/coretemp; temp will read 0. Override with --temp-input")

    mhz = read_avg_mhz()
    _check("CPU frequency (cpufreq)", True if mhz > 0 else None,
           f"{mhz} MHz" if mhz else "unavailable (MHz will read 0; cosmetic)")

    try:
        read_cpu_times()
        _check("CPU usage (/proc/stat)", True, "readable")
    except OSError:
        _check("CPU usage (/proc/stat)", None, "unreadable (usage will read 0)")

    temp = read_temp_c(temp_input) if temp_input else 0.0
    print(f"[INFO] sample frame: {build_packet(0.0, mhz, temp)[:13].hex(' ')}")

    try:
        import subprocess
        env = dict(os.environ)
        env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        state = subprocess.run(["systemctl", "--user", "is-active", "aw5d-lcd.service"],
                               capture_output=True, text=True, env=env).stdout.strip()
        _check("systemd service aw5d-lcd", True if state == "active" else None,
               state or "not installed",
               "start it with `systemctl --user start aw5d-lcd`, or run the driver directly")
    except Exception:
        pass

    launcher = shutil.which("aw5d-lcd")
    _check("aw5d-lcd command on PATH", True if launcher else None, launcher or "not found",
           "run install.sh to create ~/.local/bin/aw5d-lcd, and ensure ~/.local/bin is on your PATH")

    print()
    if ok:
        print("=> all critical checks passed; the LCD should be drivable.")
        return 0
    print("=> critical checks FAILED (see the FAIL line(s) above).")
    return 1


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="aw5d-lcd",
        description="Drive the iBUYPOWER AW5D cooler LCD from Linux (stock CPU gauge).",
    )
    p.add_argument("command", nargs="?", choices=("run", "doctor", "list"), default="run",
                   help="run (default) | doctor (diagnostics) | list (device + sensors)")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("-i", "--interval", type=float, default=_env_interval(), metavar="SECONDS",
                   help="seconds between frames (default: 1.0, or $AW5D_INTERVAL). The panel "
                        "refreshes ~1 Hz; values below ~0.5s add traffic with no visible benefit.")
    p.add_argument("-d", "--device", metavar="PATH",
                   help="hidraw node to use (default: auto-detect 3402:0407)")
    p.add_argument("--temp-input", metavar="PATH",
                   help="override the CPU temperature sysfs tempN_input path")
    p.add_argument("--once", action="store_true",
                   help="send a single frame and exit (for testing)")
    p.add_argument("--dry-run", action="store_true",
                   help="compute and print packets but do not write to the device")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="print each frame's values and bytes")
    p.add_argument("--list", action="store_true",
                   help="list the detected device + sensors, then exit")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.command == "doctor":
        return doctor()
    if args.command == "list" or args.list:
        dev = find_hidraw()
        temp_input = find_cpu_temp_input()
        print(f"device       : {dev or 'NOT FOUND'}  ({VENDOR_ID:04x}:{PRODUCT_ID:04x})")
        print(f"temp sensor  : {temp_input or 'NOT FOUND'}")
        if temp_input:
            print(f"  current    : {read_temp_c(temp_input):.1f} C")
        print(f"avg cpu mhz  : {read_avg_mhz()}")
        return 0
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
