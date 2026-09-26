#!/usr/bin/env python3
"""cTrader 版と MT5 版のログ CSV を突き合わせる（仕様書 v0.1 8 章の手順 2〜4）。

bar_time を各プラットフォームのタイムゾーンから UTC に直し、(bar_time, dir) で照合して
一致 / cTrader のみ / MT5 のみ に分類する。片側のみの足には、終値とバンドの差（pips）を付ける。

使い方:
  python3 tools/compare_logs.py ctrader.csv mt5.csv \
      --ctrader-tz UTC --mt5-tz Europe/Athens --from 2026-06-26 --to 2026-09-26 \
      -o compare_result.csv

タイムゾーンは IANA 名（例: UTC, Europe/Athens, Asia/Tokyo）か固定オフセット（例: +02:00）で指定する。
MT5 ブローカーのサーバー時刻は「GMT+2 / 夏時間 GMT+3」が多く、これは Europe/Athens と同じ動きになる。
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

TIME_FMT = "%Y-%m-%d %H:%M"


def parse_tz(spec: str) -> tzinfo:
    m = re.fullmatch(r"([+-])(\d{1,2}):?(\d{2})?", spec)
    if m:
        sign = 1 if m.group(1) == "+" else -1
        delta = timedelta(hours=int(m.group(2)), minutes=int(m.group(3) or 0))
        return timezone(sign * delta)
    return ZoneInfo(spec)


def to_utc(bar_time: str, tz: tzinfo) -> datetime:
    return datetime.strptime(bar_time, TIME_FMT).replace(tzinfo=tz).astimezone(timezone.utc)


def load(path: str, tz: tzinfo) -> Dict[Tuple[datetime, str], dict]:
    rows: Dict[Tuple[datetime, str], dict] = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = (to_utc(row["bar_time"], tz), row["dir"])
            rows[key] = row
    return rows


def band_gap_pips(row: dict, pip: float) -> float:
    """終値がバンドをどれだけ抜けたか（pips、正で抜けている）。"""
    close = float(row["close"])
    if row["dir"] == "UP":
        return (close - float(row["upper"])) / pip
    return (float(row["lower"]) - close) / pip


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ctrader_log")
    ap.add_argument("mt5_log")
    ap.add_argument("--ctrader-tz", default="UTC", help="cTrader ログの bar_time のタイムゾーン（既定 UTC）")
    ap.add_argument("--mt5-tz", default="UTC", help="MT5 ログの bar_time のタイムゾーン（サーバー時刻）")
    ap.add_argument("--from", dest="date_from", help="比較開始日（UTC、YYYY-MM-DD、含む）")
    ap.add_argument("--to", dest="date_to", help="比較終了日（UTC、YYYY-MM-DD、含む）")
    ap.add_argument("--pip", type=float, default=0.01, help="1 pip の価格幅（GBPJPY は 0.01）")
    ap.add_argument("--pass-rate", type=float, default=90.0, help="合格ライン（%%）")
    ap.add_argument("-o", "--output", help="分類結果 CSV の出力先")
    a = ap.parse_args(argv)

    ct = load(a.ctrader_log, parse_tz(a.ctrader_tz))
    mt = load(a.mt5_log, parse_tz(a.mt5_tz))

    lo = datetime.strptime(a.date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc) if a.date_from else None
    hi = (
        datetime.strptime(a.date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
        if a.date_to
        else None
    )

    def in_range(t: datetime) -> bool:
        return (lo is None or t >= lo) and (hi is None or t < hi)

    keys = sorted(k for k in set(ct) | set(mt) if in_range(k[0]))
    out_rows = []
    counts = {"match": 0, "ctrader_only": 0, "mt5_only": 0}
    for key in keys:
        t, d = key
        c, m = ct.get(key), mt.get(key)
        if c and m:
            status = "match"
        elif c:
            status = "ctrader_only"
        else:
            status = "mt5_only"
        counts[status] += 1
        out_rows.append(
            {
                "bar_time_utc": t.strftime(TIME_FMT),
                "dir": d,
                "status": status,
                "ct_close": c["close"] if c else "",
                "ct_gap_pips": f"{band_gap_pips(c, a.pip):.1f}" if c else "",
                "ct_sqlen": c["sqlen"] if c else "",
                "ct_hit": c["sq_mode_hit"] if c else "",
                "mt5_close": m["close"] if m else "",
                "mt5_gap_pips": f"{band_gap_pips(m, a.pip):.1f}" if m else "",
                "mt5_sqlen": m["sqlen"] if m else "",
                "mt5_hit": m["sq_mode_hit"] if m else "",
            }
        )

    if a.output:
        with open(a.output, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()) if out_rows else ["bar_time_utc"])
            w.writeheader()
            w.writerows(out_rows)

    total = len(keys)
    rate = counts["match"] * 100.0 / total if total else 0.0
    print(f"signals (union): {total}")
    print(f"  match        : {counts['match']}")
    print(f"  cTrader only : {counts['ctrader_only']}")
    print(f"  MT5 only     : {counts['mt5_only']}")
    print(f"match rate     : {rate:.1f}% (pass line {a.pass_rate:.0f}%) -> {'PASS' if rate >= a.pass_rate else 'FAIL'}")
    print("片側のみの足: gap_pips が小さい（数 pips 未満）なら価格差、sqlen が Sq_MinBars 付近なら SqLen 差を疑う")
    return 0


if __name__ == "__main__":
    sys.exit(main())
