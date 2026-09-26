#!/usr/bin/env python3
"""BB スクイーズ・アラート判定のリファレンス実装（仕様書 v0.1 準拠）。

cTrader 版・MT5 版と同じ式・同じループ順で計算し、同じ形式のログ CSV を出す。
両実装の突き合わせで食い違いが出たとき、どちらが仕様どおりかを確かめる基準に使う。

入力 CSV（ヘッダ必須）: time,open,high,low,close
  time は "YYYY-MM-DD HH:MM"（足の開始時刻）。古い順に並んでいること。
  最終行は確定足として扱う（形成中の足を含めない CSV を渡すこと）。

使い方:
  python3 tools/bbsq_reference.py bars.csv -o reference_log.csv --symbol GBPJPY --tf M15
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass, field
from typing import List, Optional

MODES = ("Keltner", "BandWidth", "Either", "Both")
BREAK_MODES = ("Close", "Body")

CSV_HEADER = (
    "platform,symbol,tf,bar_time,dir,open,close,upper,lower,mid,"
    "bw_pct,kc_up,kc_lo,sqlen,sq_mode_hit"
)


@dataclass
class Params:
    bb_period: int = 20
    bb_dev: float = 2.0
    kc_period: int = 20
    kc_atr_period: int = 20
    kc_mult: float = 1.5
    sq_mode: str = "Either"
    sq_min_bars: int = 6
    sq_bw_lookback: int = 120
    sq_bw_pct: float = 20.0
    break_mode: str = "Close"

    def warmup(self) -> int:
        """判定を始める最初の足のインデックス（0 始まり）。

        仕様 8 章「Sq_BwLookback + BB_Period 本以降のみ判定」を、
        インデックス >= BB_Period + Sq_BwLookback と解釈する。
        EMA/ATR の初期化が終わっていることも保証する。
        """
        return max(self.bb_period + self.sq_bw_lookback, self.kc_period, self.kc_atr_period)


@dataclass
class Bar:
    time: str
    open: float
    high: float
    low: float
    close: float


@dataclass
class Signal:
    index: int
    time: str
    direction: str  # "UP" / "DOWN"
    open: float
    close: float
    upper: float
    lower: float
    mid: float
    bw_pct: float
    kc_up: float
    kc_lo: float
    sqlen: int  # 解除直前足の SqLen
    sq_mode_hit: str  # 解除直前足で成立していた条件 KC / BW / BOTH


@dataclass
class Series:
    mid: List[float] = field(default_factory=list)
    upper: List[float] = field(default_factory=list)
    lower: List[float] = field(default_factory=list)
    ema: List[float] = field(default_factory=list)
    atr: List[float] = field(default_factory=list)
    kc_up: List[float] = field(default_factory=list)
    kc_lo: List[float] = field(default_factory=list)
    bw: List[float] = field(default_factory=list)
    bw_pct: List[float] = field(default_factory=list)
    kc_hit: List[bool] = field(default_factory=list)
    bw_hit: List[bool] = field(default_factory=list)
    sq: List[bool] = field(default_factory=list)
    sqlen: List[int] = field(default_factory=list)


NAN = float("nan")


def compute(bars: List[Bar], p: Params) -> tuple[Series, List[Signal]]:
    if p.sq_mode not in MODES:
        raise ValueError(f"sq_mode must be one of {MODES}")
    if p.break_mode not in BREAK_MODES:
        raise ValueError(f"break_mode must be one of {BREAK_MODES}")

    s = Series()
    signals: List[Signal] = []
    warm = p.warmup()
    n, q, pa, lb = p.bb_period, p.kc_period, p.kc_atr_period, p.sq_bw_lookback

    for i, b in enumerate(bars):
        # --- ボリンジャーバンド（母集団標準偏差、k=0..n-1 の順で合計） ---
        if i >= n - 1:
            total = 0.0
            for k in range(n):
                total += bars[i - k].close
            mid = total / n
            var = 0.0
            for k in range(n):
                d = bars[i - k].close - mid
                var += d * d
            sd = math.sqrt(var / n)
            upper = mid + p.bb_dev * sd
            lower = mid - p.bb_dev * sd
            bw = (upper - lower) / mid
        else:
            mid = upper = lower = bw = NAN
        s.mid.append(mid)
        s.upper.append(upper)
        s.lower.append(lower)
        s.bw.append(bw)

        # --- EMA（初期値は最初の q 本の SMA、足 q-1 に置く） ---
        if i == q - 1:
            total = 0.0
            for k in range(q):
                total += bars[i - k].close
            ema = total / q
        elif i >= q:
            alpha = 2.0 / (q + 1)
            ema = s.ema[i - 1] + alpha * (b.close - s.ema[i - 1])
        else:
            ema = NAN
        s.ema.append(ema)

        # --- ATR（Wilder、TR_0 = High_0 - Low_0、初期値は最初の p 本の TR 平均） ---
        if i == pa - 1:
            total = 0.0
            for k in range(pa):
                total += true_range(bars, i - k)
            atr = total / pa
        elif i >= pa:
            atr = ((pa - 1) * s.atr[i - 1] + true_range(bars, i)) / pa
        else:
            atr = NAN
        s.atr.append(atr)

        kc_up = ema + p.kc_mult * atr
        kc_lo = ema - p.kc_mult * atr
        s.kc_up.append(kc_up)
        s.kc_lo.append(kc_lo)

        # --- BW パーセンタイル（足 i を含む直近 lb 本、BW_i 以下の本数 / lb） ---
        if i >= n - 1 + lb - 1:
            cnt = 0
            for k in range(lb):
                if s.bw[i - k] <= bw:
                    cnt += 1
            bw_pct = cnt * 100.0 / lb
        else:
            bw_pct = NAN
        s.bw_pct.append(bw_pct)

        # --- スクイーズ状態 ---
        if i >= warm:
            kc_hit = upper <= kc_up and lower >= kc_lo
            bw_hit = bw_pct <= p.sq_bw_pct
            sq = squeeze(p.sq_mode, kc_hit, bw_hit)
        else:
            kc_hit = bw_hit = sq = False
        s.kc_hit.append(kc_hit)
        s.bw_hit.append(bw_hit)
        s.sq.append(sq)
        prev_len = s.sqlen[i - 1] if i > 0 else 0
        s.sqlen.append(prev_len + 1 if sq else 0)

        # --- 発火判定（足 i 自身のバンドで判定） ---
        if i > warm and s.sqlen[i - 1] >= p.sq_min_bars and not sq:
            d = breakout(p.break_mode, b.open, b.close, upper, lower)
            if d:
                signals.append(
                    Signal(
                        index=i,
                        time=b.time,
                        direction=d,
                        open=b.open,
                        close=b.close,
                        upper=upper,
                        lower=lower,
                        mid=mid,
                        bw_pct=bw_pct,
                        kc_up=kc_up,
                        kc_lo=kc_lo,
                        sqlen=s.sqlen[i - 1],
                        sq_mode_hit=hit_label(s.kc_hit[i - 1], s.bw_hit[i - 1]),
                    )
                )
    return s, signals


def true_range(bars: List[Bar], i: int) -> float:
    b = bars[i]
    if i == 0:
        return b.high - b.low
    pc = bars[i - 1].close
    return max(b.high - b.low, abs(b.high - pc), abs(b.low - pc))


def squeeze(mode: str, kc_hit: bool, bw_hit: bool) -> bool:
    if mode == "Keltner":
        return kc_hit
    if mode == "BandWidth":
        return bw_hit
    if mode == "Either":
        return kc_hit or bw_hit
    return kc_hit and bw_hit


def breakout(mode: str, o: float, c: float, upper: float, lower: float) -> Optional[str]:
    if mode == "Close":
        if c > upper:
            return "UP"
        if c < lower:
            return "DOWN"
        return None
    if min(o, c) > upper:
        return "UP"
    if max(o, c) < lower:
        return "DOWN"
    return None


def hit_label(kc_hit: bool, bw_hit: bool) -> str:
    if kc_hit and bw_hit:
        return "BOTH"
    if kc_hit:
        return "KC"
    if bw_hit:
        return "BW"
    return ""


def format_row(platform: str, symbol: str, tf: str, sig: Signal) -> str:
    return ",".join(
        [
            platform,
            symbol,
            tf,
            sig.time,
            sig.direction,
            f"{sig.open:.3f}",
            f"{sig.close:.3f}",
            f"{sig.upper:.3f}",
            f"{sig.lower:.3f}",
            f"{sig.mid:.3f}",
            f"{sig.bw_pct:.1f}",
            f"{sig.kc_up:.3f}",
            f"{sig.kc_lo:.3f}",
            str(sig.sqlen),
            sig.sq_mode_hit,
        ]
    )


def format_message(symbol: str, tf: str, sig: Signal) -> str:
    band = f"upper={sig.upper:.3f}" if sig.direction == "UP" else f"lower={sig.lower:.3f}"
    return f"BBSQ {symbol} {tf} {sig.direction} {sig.time} close={sig.close:.3f} {band} sqlen={sig.sqlen}"


def load_bars(path: str) -> List[Bar]:
    bars: List[Bar] = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            bars.append(
                Bar(
                    time=row["time"].strip(),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                )
            )
    return bars


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bars", help="OHLC CSV (time,open,high,low,close)")
    ap.add_argument("-o", "--output", help="ログ CSV の出力先（省略時は標準出力）")
    ap.add_argument("--platform", default="Reference")
    ap.add_argument("--symbol", default="GBPJPY")
    ap.add_argument("--tf", default="M15")
    ap.add_argument("--bb-period", type=int, default=20)
    ap.add_argument("--bb-dev", type=float, default=2.0)
    ap.add_argument("--kc-period", type=int, default=20)
    ap.add_argument("--kc-atr-period", type=int, default=20)
    ap.add_argument("--kc-mult", type=float, default=1.5)
    ap.add_argument("--sq-mode", choices=MODES, default="Either")
    ap.add_argument("--sq-min-bars", type=int, default=6)
    ap.add_argument("--sq-bw-lookback", type=int, default=120)
    ap.add_argument("--sq-bw-pct", type=float, default=20.0)
    ap.add_argument("--break-mode", choices=BREAK_MODES, default="Close")
    a = ap.parse_args(argv)

    p = Params(
        bb_period=a.bb_period,
        bb_dev=a.bb_dev,
        kc_period=a.kc_period,
        kc_atr_period=a.kc_atr_period,
        kc_mult=a.kc_mult,
        sq_mode=a.sq_mode,
        sq_min_bars=a.sq_min_bars,
        sq_bw_lookback=a.sq_bw_lookback,
        sq_bw_pct=a.sq_bw_pct,
        break_mode=a.break_mode,
    )
    _, signals = compute(load_bars(a.bars), p)
    lines = [CSV_HEADER] + [format_row(a.platform, a.symbol, a.tf, sg) for sg in signals]
    text = "\n".join(lines) + "\n"
    if a.output:
        with open(a.output, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
