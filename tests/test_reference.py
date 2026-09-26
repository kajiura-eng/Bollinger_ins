import io
import math
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import bbsq_reference as ref  # noqa: E402
import compare_logs  # noqa: E402

# 計算式の検算用（小さい期間）
TINY = dict(bb_period=5, bb_dev=2.0, kc_period=5, kc_atr_period=5, kc_mult=1.5,
            sq_min_bars=3, sq_bw_lookback=10, sq_bw_pct=20.0)
# 発火判定用。BB_Period=5 だと母集団σでは外れ値 1 本の z が最大 (n-1)/sqrt(n)=1.79 で 2σ を抜けないため 10 にする
SMALL = dict(bb_period=10, bb_dev=2.0, kc_period=10, kc_atr_period=10, kc_mult=1.5,
             sq_min_bars=3, sq_bw_lookback=20, sq_bw_pct=20.0)


def make_bars(closes, spread=0.02, opens=None):
    bars = []
    for i, c in enumerate(closes):
        o = opens[i] if opens else (closes[i - 1] if i else c)
        bars.append(ref.Bar(time=f"2026-09-22 {i // 4:02d}:{(i % 4) * 15:02d}", open=o,
                            high=max(o, c) + spread, low=min(o, c) - spread, close=c))
    return bars


def squeeze_then(*finals, quiet=15, amp=0.05, decay=0.9):
    """0.5 刻みのジグザグ（BB が広い）→ 振幅が減衰する横ばい（スクイーズ）→ finals の各足。

    finals は横ばい水準からの終値の変化幅。始値は前の足の終値。
    """
    closes, v = [], 100.0
    for i in range(60):
        v += 0.5 if (i // 10) % 2 == 0 else -0.5
        closes.append(v)
    closes += [v + (amp if i % 2 else -amp) * decay ** i for i in range(quiet)]
    closes += [v + f for f in finals]
    return make_bars(closes, spread=0.001)


class FormulaTests(unittest.TestCase):
    def test_bollinger_population_std(self):
        closes = [1, 2, 3, 4, 5, 6]
        s, _ = ref.compute(make_bars(closes), ref.Params(**TINY))
        mid = 4.0  # (2+3+4+5+6)/5
        sd = math.sqrt(sum((c - mid) ** 2 for c in [2, 3, 4, 5, 6]) / 5)
        self.assertAlmostEqual(s.mid[5], mid)
        self.assertAlmostEqual(s.upper[5], mid + 2 * sd)
        self.assertAlmostEqual(s.lower[5], mid - 2 * sd)
        self.assertTrue(math.isnan(s.mid[3]))

    def test_ema_seed_and_recursion(self):
        closes = [1, 2, 3, 4, 5, 11]
        s, _ = ref.compute(make_bars(closes), ref.Params(**TINY))
        self.assertAlmostEqual(s.ema[4], 3.0)
        self.assertAlmostEqual(s.ema[5], 3.0 + (2 / 6) * (11 - 3.0))

    def test_atr_wilder(self):
        bars = [ref.Bar("t", 10, 11, 9, 10) for _ in range(5)]  # TR = 2
        bars.append(ref.Bar("t", 10, 16, 10, 15))  # TR = max(6, 6, 0) = 6
        s, _ = ref.compute(bars, ref.Params(**TINY))
        self.assertAlmostEqual(s.atr[4], 2.0)
        self.assertAlmostEqual(s.atr[5], (4 * 2.0 + 6) / 5)

    def test_bw_percentile_rank_one(self):
        # BW が単調に縮む -> 最新足は窓内で最小 -> 1/lookback*100
        closes = [100 + ((-1) ** i) * (20 - i * 0.5) for i in range(30)]
        s, _ = ref.compute(make_bars(closes), ref.Params(**TINY))
        self.assertAlmostEqual(s.bw_pct[-1], 100.0 / TINY["sq_bw_lookback"])

    def test_no_squeeze_before_warmup(self):
        p = ref.Params(**SMALL)
        s, _ = ref.compute(squeeze_then(1.0), p)
        self.assertFalse(any(s.sq[: p.warmup()]))


class SignalTests(unittest.TestCase):
    def test_up_breakout_fires_on_release_bar(self):
        bars = squeeze_then(1.0)
        s, sigs = ref.compute(bars, ref.Params(**SMALL))
        self.assertEqual(len(sigs), 1)
        sig = sigs[0]
        self.assertEqual(sig.index, len(bars) - 1)
        self.assertEqual(sig.direction, "UP")
        self.assertFalse(s.sq[-1])
        self.assertGreaterEqual(sig.sqlen, SMALL["sq_min_bars"])
        self.assertEqual(sig.sqlen, s.sqlen[-2])
        self.assertGreater(sig.close, sig.upper)  # 足 i 自身のバンド

    def test_down_breakout(self):
        _, sigs = ref.compute(squeeze_then(-1.0), ref.Params(**SMALL))
        self.assertEqual([x.direction for x in sigs], ["DOWN"])

    def test_release_without_break_is_consumed(self):
        # BandWidth 分位だけで解除（終値はバンド内）-> 発火なし。次の足で大きく抜けても発火しない
        p = ref.Params(**{**SMALL, "sq_mode": "BandWidth", "sq_bw_pct": 5.0})
        bars = squeeze_then(0.03, 1.0)
        s, sigs = ref.compute(bars, p)
        self.assertGreaterEqual(s.sqlen[-3], p.sq_min_bars)
        self.assertFalse(s.sq[-2], "解除足でスクイーズが外れていること")
        self.assertLessEqual(bars[-2].close, s.upper[-2], "解除足の終値はバンド内")
        self.assertGreater(bars[-1].close, s.upper[-1], "次の足は抜けている")
        self.assertEqual(sigs, [])

    def test_body_mode_requires_open_outside(self):
        p_close = ref.Params(**SMALL, break_mode="Close")
        p_body = ref.Params(**SMALL, break_mode="Body")
        bars = squeeze_then(1.0)  # 始値はバンド内
        self.assertEqual(len(ref.compute(bars, p_close)[1]), 1)
        self.assertEqual(len(ref.compute(bars, p_body)[1]), 0)

    def test_min_bars_gate(self):
        _, sigs = ref.compute(squeeze_then(1.0, quiet=3), ref.Params(**{**SMALL, "sq_min_bars": 10}))
        self.assertEqual(sigs, [])

    def test_modes(self):
        bars = squeeze_then(1.0)
        for mode in ref.MODES:
            s, _ = ref.compute(bars, ref.Params(**SMALL, sq_mode=mode))
            for kc, bw, sq in zip(s.kc_hit, s.bw_hit, s.sq):
                self.assertEqual(sq, ref.squeeze(mode, kc, bw))


class FormatTests(unittest.TestCase):
    def sample(self):
        return ref.Signal(index=0, time="2026-09-22 16:30", direction="DOWN", open=210.552, close=210.438,
                          upper=210.789, lower=210.463, mid=210.626, bw_pct=12.5, kc_up=210.801,
                          kc_lo=210.451, sqlen=8, sq_mode_hit="KC")

    def test_message_matches_spec_example(self):
        self.assertEqual(ref.format_message("GBPJPY", "M15", self.sample()),
                         "BBSQ GBPJPY M15 DOWN 2026-09-22 16:30 close=210.438 lower=210.463 sqlen=8")

    def test_csv_row_matches_spec_example(self):
        self.assertEqual(ref.format_row("cTrader", "GBPJPY", "M15", self.sample()),
                         "cTrader,GBPJPY,M15,2026-09-22 16:30,DOWN,210.552,210.438,210.789,210.463,"
                         "210.626,12.5,210.801,210.451,8,KC")


class CompareTests(unittest.TestCase):
    def test_classification_with_tz_offset(self):
        head = ref.CSV_HEADER + "\n"
        ct = head + "cTrader,GBPJPY,M15,2026-09-22 13:30,DOWN,1,210.438,2,210.463,1,1,1,1,8,KC\n" \
                    "cTrader,GBPJPY,M15,2026-09-22 14:00,UP,1,210.900,210.890,1,1,1,1,1,7,BW\n"
        mt = head + "MT5,GBPJPY,M15,2026-09-22 16:30,DOWN,1,210.440,2,210.461,1,1,1,1,8,KC\n" \
                    "MT5,GBPJPY,M15,2026-09-22 18:00,DOWN,1,210.000,2,210.100,1,1,1,1,6,BOTH\n"
        with tempfile.TemporaryDirectory() as d:
            pc, pm, po = (os.path.join(d, x) for x in ("c.csv", "m.csv", "o.csv"))
            for path, text in ((pc, ct), (pm, mt)):
                with open(path, "w") as f:
                    f.write(text)
            out = io.StringIO()
            with redirect_stdout(out):
                compare_logs.main([pc, pm, "--ctrader-tz", "UTC", "--mt5-tz", "Europe/Athens", "-o", po])
            text = out.getvalue()
            self.assertIn("match        : 1", text)
            self.assertIn("cTrader only : 1", text)
            self.assertIn("MT5 only     : 1", text)
            with open(po) as f:
                rows = f.read()
            self.assertIn("2026-09-22 14:00,UP,ctrader_only,210.900,1.0", rows)


if __name__ == "__main__":
    unittest.main()
