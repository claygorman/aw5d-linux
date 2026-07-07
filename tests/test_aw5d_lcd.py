"""Unit tests for aw5d_lcd.

Pure-logic tests (packet building, usage math, env parsing) — no device or sysfs
needed, so they run anywhere. Run with:

    python3 -m unittest discover -s tests        # or: just test
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import aw5d_lcd as a  # noqa: E402


class BuildPacketTest(unittest.TestCase):
    def test_golden_idle_packet_matches_captured(self):
        # Captured from the vendor helper at idle (usage 8%, 3753 MHz, 59 C) —
        # see RESEARCH.md. At idle even the cosmetic bytes line up exactly.
        pkt = a.build_packet(8, 3753, 59)
        self.assertEqual(len(pkt), a.REPORT_LEN)
        self.assertEqual(pkt[:13].hex(), "1008080ea93b000000080502f0")
        self.assertEqual(pkt[13:], bytes(a.REPORT_LEN - 13))  # zero-padded tail

    def test_header_and_reserved_bytes(self):
        pkt = a.build_packet(0, 0, 0)
        self.assertEqual(pkt[0], a.REPORT_ID)      # report id 0x10
        self.assertEqual(pkt[1], 0x08)             # constant packet type
        self.assertEqual(pkt[6:9], b"\x00\x00\x00")  # reserved

    def test_usage_is_byte2_rounded_and_clamped(self):
        self.assertEqual(a.build_packet(8, 0, 0)[2], 8)
        self.assertEqual(a.build_packet(8.6, 0, 0)[2], 9)    # rounds
        self.assertEqual(a.build_packet(150, 0, 0)[2], 100)  # clamp high
        self.assertEqual(a.build_packet(-5, 0, 0)[2], 0)     # clamp low

    def test_mhz_is_bytes3_4_big_endian(self):
        # (mhz, hi, lo) — validated against HWiNFO + the on-screen photo in RESEARCH.md
        for mhz, hi, lo in [(3753, 0x0e, 0xa9), (3810, 0x0e, 0xe2),
                            (3697, 0x0e, 0x71), (3963, 0x0f, 0x7b),
                            (4344, 0x10, 0xf8)]:
            pkt = a.build_packet(0, mhz, 0)
            self.assertEqual((pkt[3], pkt[4]), (hi, lo), f"mhz={mhz}")
            self.assertEqual((pkt[3] << 8) | pkt[4], mhz, f"mhz={mhz}")

    def test_mhz_clamped_to_uint16(self):
        pkt = a.build_packet(0, 70000, 0)
        self.assertEqual((pkt[3], pkt[4]), (0xff, 0xff))

    def test_temp_is_byte5_rounded_and_clamped(self):
        self.assertEqual(a.build_packet(0, 0, 59)[5], 59)
        self.assertEqual(a.build_packet(0, 0, 59.6)[5], 60)    # rounds
        self.assertEqual(a.build_packet(0, 0, 300)[5], 0xff)   # clamp

    def test_hot_or_busy_styling_flag(self):
        self.assertEqual(a.build_packet(10, 3000, 50)[12], 0xf0)  # normal
        self.assertEqual(a.build_packet(10, 3000, 83)[12], 0xf9)  # hot (temp >= 80)
        self.assertEqual(a.build_packet(99, 3000, 50)[12], 0xf9)  # busy (usage >= 90)

    def test_all_byte_values_fit_in_a_byte(self):
        for u, m, t in [(0, 0, 0), (100, 65535, 255), (50, 4200, 72), (37, 3333, 61)]:
            for b in a.build_packet(u, m, t):
                self.assertTrue(0 <= b <= 255)


class CpuUsageTest(unittest.TestCase):
    def test_half_busy(self):
        # dtotal=100, didle=50 -> 50%
        self.assertAlmostEqual(a.cpu_usage_pct((100, 100), (200, 150)), 50.0)

    def test_zero_delta_is_zero(self):
        self.assertEqual(a.cpu_usage_pct((100, 50), (100, 50)), 0.0)

    def test_fully_busy(self):
        # dtotal=100, didle=0 -> 100%
        self.assertAlmostEqual(a.cpu_usage_pct((0, 0), (100, 0)), 100.0)

    def test_result_is_clamped_0_100(self):
        self.assertEqual(a.cpu_usage_pct((100, 0), (50, 0)), 0.0)  # negative dtotal


class EnvIntervalTest(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get("AW5D_INTERVAL")

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("AW5D_INTERVAL", None)
        else:
            os.environ["AW5D_INTERVAL"] = self._saved

    def test_default_when_unset(self):
        os.environ.pop("AW5D_INTERVAL", None)
        self.assertEqual(a._env_interval(), a.DEFAULT_INTERVAL)

    def test_reads_env_value(self):
        os.environ["AW5D_INTERVAL"] = "3"
        self.assertEqual(a._env_interval(), 3.0)

    def test_invalid_falls_back_to_default(self):
        os.environ["AW5D_INTERVAL"] = "not-a-number"
        self.assertEqual(a._env_interval(), a.DEFAULT_INTERVAL)


class ParseArgsTest(unittest.TestCase):
    def test_default_command_is_run(self):
        self.assertEqual(a.parse_args([]).command, "run")

    def test_all_commands_recognized(self):
        for cmd in ("run", "doctor", "list", "self-update"):
            self.assertEqual(a.parse_args([cmd]).command, cmd)


if __name__ == "__main__":
    unittest.main()
