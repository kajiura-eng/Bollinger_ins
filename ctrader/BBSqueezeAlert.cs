// BB スクイーズ・アラートインジケータ（cTrader Automate C# Indicator）
// 仕様: docs/bb_alert_indicator_spec_v0_1.md（v0.1）。判定ロジックは仕様書が唯一の正。
//
// - 判定は確定足のみ。Calculate(index) で index-1（直近確定足）までを 1 回ずつ評価する
// - BB / EMA / ATR / BandWidth 分位はすべて自前計算（組込指標は使わない）
// - 通知はチャート内テキスト + 音のみ。起動時の過去足では通知しない（描画とログは行う）
// - ログ CSV は Documents\cAlgo\Data\<Log_FileName>（空なら bb_alert_log_<SYMBOL>_<TF>.csv）。
//   起動時と過去足の追加読込時に作り直し、以後は追記
// - 過去足の追加読込（Calculate が古い index で呼び直される）では描画・ログを作り直し、通知は出さない
// - Dump_Bars=true なら初回ロード完了時に確定足の OHLC を bars_<SYMBOL>_<TF>.csv へ出力（bbsq_reference.py の入力）
// - 足の時刻は UTC（TimeZone = TimeZones.UTC）。MT5 ログとの突き合わせは tools/compare_logs.py で補正する

using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using cAlgo.API;

namespace cAlgo
{
    public enum SqMode
    {
        Keltner,
        BandWidth,
        Either,
        Both
    }

    public enum BreakMode
    {
        Close,
        Body
    }

    [Indicator(IsOverlay = true, TimeZone = TimeZones.UTC, AccessRights = AccessRights.FullAccess)]
    public class BBSqueezeAlert : Indicator
    {
        // ---- 共通パラメータ（仕様 2 章。名前・型・既定値を MT5 版と一致させる） ----
        [Parameter("BB_Period", DefaultValue = 20, MinValue = 2, Group = "BB")]
        public int BB_Period { get; set; }

        [Parameter("BB_Dev", DefaultValue = 2.0, MinValue = 0.1, Group = "BB")]
        public double BB_Dev { get; set; }

        [Parameter("KC_Period", DefaultValue = 20, MinValue = 1, Group = "Keltner")]
        public int KC_Period { get; set; }

        [Parameter("KC_AtrPeriod", DefaultValue = 20, MinValue = 1, Group = "Keltner")]
        public int KC_AtrPeriod { get; set; }

        [Parameter("KC_Mult", DefaultValue = 1.5, MinValue = 0.1, Group = "Keltner")]
        public double KC_Mult { get; set; }

        [Parameter("Sq_Mode", DefaultValue = SqMode.Either, Group = "Squeeze")]
        public SqMode Sq_Mode { get; set; }

        [Parameter("Sq_MinBars", DefaultValue = 6, MinValue = 1, Group = "Squeeze")]
        public int Sq_MinBars { get; set; }

        [Parameter("Sq_BwLookback", DefaultValue = 120, MinValue = 1, Group = "Squeeze")]
        public int Sq_BwLookback { get; set; }

        [Parameter("Sq_BwPct", DefaultValue = 20.0, MinValue = 0.0, MaxValue = 100.0, Group = "Squeeze")]
        public double Sq_BwPct { get; set; }

        [Parameter("Break_Mode", DefaultValue = BreakMode.Close, Group = "Squeeze")]
        public BreakMode Break_Mode { get; set; }

        [Parameter("Alert_Enabled", DefaultValue = true, Group = "Output")]
        public bool Alert_Enabled { get; set; }

        [Parameter("Log_Enabled", DefaultValue = true, Group = "Output")]
        public bool Log_Enabled { get; set; }

        [Parameter("Log_FileName", DefaultValue = "", Group = "Output")]
        public string Log_FileName { get; set; }

        // ---- 実装固有パラメータ（判定には関与しない） ----
        [Parameter("Sound_File", DefaultValue = "", Group = "Output")]
        public string Sound_File { get; set; }

        [Parameter("Dump_Bars", DefaultValue = false, Group = "Output")]
        public bool Dump_Bars { get; set; }

        [Parameter("Show_Keltner", DefaultValue = false, Group = "Display")]
        public bool Show_Keltner { get; set; }

        // ---- 描画 ----
        [Output("BB Upper", LineColor = "DodgerBlue")]
        public IndicatorDataSeries Upper { get; set; }

        [Output("BB Mid", LineColor = "Gray", LineStyle = LineStyle.Dots)]
        public IndicatorDataSeries Mid { get; set; }

        [Output("BB Lower", LineColor = "DodgerBlue")]
        public IndicatorDataSeries Lower { get; set; }

        [Output("KC Upper", LineColor = "Orange", LineStyle = LineStyle.Lines)]
        public IndicatorDataSeries KcUpper { get; set; }

        [Output("KC Lower", LineColor = "Orange", LineStyle = LineStyle.Lines)]
        public IndicatorDataSeries KcLower { get; set; }

        [Output("Squeeze", LineColor = "#60A9A9A9", PlotType = PlotType.Points, Thickness = 2)]
        public IndicatorDataSeries SqDotWeak { get; set; }

        [Output("Squeeze >= MinBars", LineColor = "#FF505050", PlotType = PlotType.Points, Thickness = 3)]
        public IndicatorDataSeries SqDotStrong { get; set; }

        // ---- 内部計算（足インデックスで保持） ----
        private IndicatorDataSeries _ema;
        private IndicatorDataSeries _atr;
        private IndicatorDataSeries _bw;
        private IndicatorDataSeries _bwPct;
        private IndicatorDataSeries _kcHit;   // 1 / 0
        private IndicatorDataSeries _bwHit;   // 1 / 0
        private IndicatorDataSeries _sqLen;   // Sq[i]=false なら 0

        private int _processed = -1;          // 評価済みの最後の確定足
        private bool _live;                   // 初回ロード完了後のみ通知する
        private DateTime _lastAlertBar = DateTime.MinValue;
        private string _dataDir;
        private string _logPath;
        private string _tf;

        private const string ObjPrefix = "BBSQ_";

        private static readonly CultureInfo Inv = CultureInfo.InvariantCulture;
        private const string CsvHeader =
            "platform,symbol,tf,bar_time,dir,open,close,upper,lower,mid,bw_pct,kc_up,kc_lo,sqlen,sq_mode_hit";

        protected override void Initialize()
        {
            _ema = CreateDataSeries();
            _atr = CreateDataSeries();
            _bw = CreateDataSeries();
            _bwPct = CreateDataSeries();
            _kcHit = CreateDataSeries();
            _bwHit = CreateDataSeries();
            _sqLen = CreateDataSeries();

            _tf = TimeFrameLabel(TimeFrame);
            _dataDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "cAlgo", "Data");
            string logName = string.IsNullOrWhiteSpace(Log_FileName)
                ? "bb_alert_log_" + SymbolName + "_" + _tf + ".csv"
                : Log_FileName;
            _logPath = Path.Combine(_dataDir, SafeFileName(logName));

            // 起動時は作り直す（過去足分をこの後書き出す）
            ResetLog();
        }

        public override void Calculate(int index)
        {
            // 過去足の追加読込: 評価済みより古い index から呼び直される -> 全足を再計算する
            // （最終足の tick ごとの呼び出しは index > _processed なので該当しない）
            if (index <= _processed && index < Bars.Count - 1)
                ResetForRecalc();

            // 形成中の足（index）は判定・描画しない。index-1 までの確定足を 1 本ずつ評価する
            int lastClosed = index - 1;
            while (_processed < lastClosed)
            {
                _processed++;
                Process(_processed);
            }

            if (IsLastBar)
            {
                ClearOutputs(index);
                // 最終足に到達した時点で初回ロード（または再計算）完了。以後に確定した足だけ通知する
                if (!_live)
                {
                    _live = true;
                    if (Dump_Bars)
                        DumpBars(lastClosed);
                }
            }
        }

        private void ResetForRecalc()
        {
            _processed = -1;
            _live = false;
            foreach (var obj in Chart.Objects.Where(o => o.Name.StartsWith(ObjPrefix, StringComparison.Ordinal)).ToArray())
                Chart.RemoveObject(obj.Name);
            ResetLog();
        }

        private void ResetLog()
        {
            if (!Log_Enabled || _logPath == null)
                return;
            try
            {
                Directory.CreateDirectory(_dataDir);
                System.IO.File.WriteAllText(_logPath, CsvHeader + Environment.NewLine, new UTF8Encoding(false));
            }
            catch (Exception ex)
            {
                Print("BBSQ: log file init failed: " + ex.Message);
                _logPath = null;
            }
        }

        // 確定足 0..lastClosed の OHLC を bbsq_reference.py の入力形式で書き出す
        private void DumpBars(int lastClosed)
        {
            string path = Path.Combine(_dataDir, SafeFileName("bars_" + SymbolName + "_" + _tf + ".csv"));
            string fmt = "F" + Symbol.Digits.ToString(Inv);
            try
            {
                Directory.CreateDirectory(_dataDir);
                var sb = new StringBuilder();
                sb.Append("time,open,high,low,close").Append(Environment.NewLine);
                for (int i = 0; i <= lastClosed; i++)
                {
                    sb.Append(Bars.OpenTimes[i].ToString("yyyy-MM-dd HH:mm", Inv)).Append(',')
                      .Append(Bars.OpenPrices[i].ToString(fmt, Inv)).Append(',')
                      .Append(Bars.HighPrices[i].ToString(fmt, Inv)).Append(',')
                      .Append(Bars.LowPrices[i].ToString(fmt, Inv)).Append(',')
                      .Append(Bars.ClosePrices[i].ToString(fmt, Inv)).Append(Environment.NewLine);
                }
                System.IO.File.WriteAllText(path, sb.ToString(), new UTF8Encoding(false));
                Print("BBSQ: dumped " + (lastClosed + 1) + " bars to " + path);
            }
            catch (Exception ex)
            {
                Print("BBSQ: bar dump failed: " + ex.Message);
            }
        }

        // 形成中の足には何も描かない
        private void ClearOutputs(int i)
        {
            Upper[i] = double.NaN;
            Mid[i] = double.NaN;
            Lower[i] = double.NaN;
            KcUpper[i] = double.NaN;
            KcLower[i] = double.NaN;
            SqDotWeak[i] = double.NaN;
            SqDotStrong[i] = double.NaN;
        }

        private void Process(int i)
        {
            int n = BB_Period, q = KC_Period, p = KC_AtrPeriod, lb = Sq_BwLookback;
            int warm = Math.Max(BB_Period + Sq_BwLookback, Math.Max(KC_Period, KC_AtrPeriod));

            // ---- ボリンジャーバンド（母集団標準偏差） ----
            double mid = double.NaN, upper = double.NaN, lower = double.NaN, bw = double.NaN;
            if (i >= n - 1)
            {
                double sum = 0.0;
                for (int k = 0; k < n; k++)
                    sum += Bars.ClosePrices[i - k];
                mid = sum / n;
                double sumSq = 0.0;
                for (int k = 0; k < n; k++)
                {
                    double d = Bars.ClosePrices[i - k] - mid;
                    sumSq += d * d;
                }
                double sd = Math.Sqrt(sumSq / n);
                upper = mid + BB_Dev * sd;
                lower = mid - BB_Dev * sd;
                bw = (upper - lower) / mid;
            }
            _bw[i] = bw;

            // ---- EMA（初期値は最初の q 本の SMA） ----
            double ema = double.NaN;
            if (i == q - 1)
            {
                double sum = 0.0;
                for (int k = 0; k < q; k++)
                    sum += Bars.ClosePrices[i - k];
                ema = sum / q;
            }
            else if (i >= q)
            {
                double alpha = 2.0 / (q + 1);
                ema = _ema[i - 1] + alpha * (Bars.ClosePrices[i] - _ema[i - 1]);
            }
            _ema[i] = ema;

            // ---- ATR（Wilder。TR_0 = High_0 - Low_0、初期値は最初の p 本の TR 平均） ----
            double atr = double.NaN;
            if (i == p - 1)
            {
                double sum = 0.0;
                for (int k = 0; k < p; k++)
                    sum += TrueRange(i - k);
                atr = sum / p;
            }
            else if (i >= p)
            {
                atr = ((p - 1) * _atr[i - 1] + TrueRange(i)) / p;
            }
            _atr[i] = atr;

            double kcUp = ema + KC_Mult * atr;
            double kcLo = ema - KC_Mult * atr;

            // ---- BandWidth 分位（足 i を含む直近 lb 本で BW_i 以下の本数 / lb） ----
            double bwPct = double.NaN;
            if (i >= n - 1 + lb - 1)
            {
                int cnt = 0;
                for (int k = 0; k < lb; k++)
                {
                    if (_bw[i - k] <= bw)
                        cnt++;
                }
                bwPct = cnt * 100.0 / lb;
            }
            _bwPct[i] = bwPct;

            // ---- スクイーズ状態 / 継続本数 ----
            bool kcHit = false, bwHit = false, sq = false;
            if (i >= warm)
            {
                kcHit = upper <= kcUp && lower >= kcLo;
                bwHit = bwPct <= Sq_BwPct;
                sq = IsSqueeze(kcHit, bwHit);
            }
            _kcHit[i] = kcHit ? 1.0 : 0.0;
            _bwHit[i] = bwHit ? 1.0 : 0.0;
            int prevLen = i > 0 ? (int)_sqLen[i - 1] : 0;
            int sqLen = sq ? prevLen + 1 : 0;
            _sqLen[i] = sqLen;

            // ---- 描画（確定足のみ） ----
            Upper[i] = upper;
            Mid[i] = mid;
            Lower[i] = lower;
            KcUpper[i] = Show_Keltner ? kcUp : double.NaN;
            KcLower[i] = Show_Keltner ? kcLo : double.NaN;
            double dotY = lower - 0.5 * atr;
            SqDotWeak[i] = sq && sqLen < Sq_MinBars ? dotY : double.NaN;
            SqDotStrong[i] = sq && sqLen >= Sq_MinBars ? dotY : double.NaN;

            // ---- 発火判定（足 i 自身のバンドで判定） ----
            if (i <= warm || sq || prevLen < Sq_MinBars)
                return;

            double o = Bars.OpenPrices[i], c = Bars.ClosePrices[i];
            string dir = null;
            if (Break_Mode == BreakMode.Close)
            {
                if (c > upper) dir = "UP";
                else if (c < lower) dir = "DOWN";
            }
            else
            {
                if (Math.Min(o, c) > upper) dir = "UP";
                else if (Math.Max(o, c) < lower) dir = "DOWN";
            }
            if (dir == null)
                return; // 解除したが発火なし（この解除は消費済み）

            DateTime t = Bars.OpenTimes[i];
            string hit = HitLabel(_kcHit[i - 1] > 0.5, _bwHit[i - 1] > 0.5);

            // 矢印
            if (dir == "UP")
                Chart.DrawIcon(ObjPrefix + t.Ticks, ChartIconType.UpArrow, t, Bars.HighPrices[i] + 0.3 * atr, Color.LimeGreen);
            else
                Chart.DrawIcon(ObjPrefix + t.Ticks, ChartIconType.DownArrow, t, Bars.LowPrices[i] - 0.3 * atr, Color.Red);

            // ログ（過去足も書く）
            if (Log_Enabled && _logPath != null)
            {
                string row = string.Join(",",
                    "cTrader", SymbolName, _tf, t.ToString("yyyy-MM-dd HH:mm", Inv), dir,
                    F3(o), F3(c), F3(upper), F3(lower), F3(mid), bwPct.ToString("F1", Inv),
                    F3(kcUp), F3(kcLo), prevLen.ToString(Inv), hit);
                try
                {
                    System.IO.File.AppendAllText(_logPath, row + Environment.NewLine, new UTF8Encoding(false));
                }
                catch (Exception ex)
                {
                    Print("BBSQ: log write failed: " + ex.Message);
                }
            }

            // 通知（初回ロード中は出さない。同じ足では 1 回だけ）
            if (!_live || !Alert_Enabled || t == _lastAlertBar)
                return;
            _lastAlertBar = t;

            string msg = string.Format(Inv, "BBSQ {0} {1} {2} {3} close={4} {5}={6} sqlen={7}",
                SymbolName, _tf, dir, t.ToString("yyyy-MM-dd HH:mm", Inv), F3(c),
                dir == "UP" ? "upper" : "lower", F3(dir == "UP" ? upper : lower), prevLen);
            Print(msg);
            Chart.DrawStaticText(ObjPrefix + "msg", msg, VerticalAlignment.Top, HorizontalAlignment.Left,
                dir == "UP" ? Color.LimeGreen : Color.Red);
            if (!string.IsNullOrEmpty(Sound_File))
                Notifications.PlaySound(Sound_File);
        }

        private double TrueRange(int i)
        {
            double h = Bars.HighPrices[i], l = Bars.LowPrices[i];
            if (i == 0)
                return h - l;
            double pc = Bars.ClosePrices[i - 1];
            return Math.Max(h - l, Math.Max(Math.Abs(h - pc), Math.Abs(l - pc)));
        }

        private bool IsSqueeze(bool kcHit, bool bwHit)
        {
            switch (Sq_Mode)
            {
                case SqMode.Keltner: return kcHit;
                case SqMode.BandWidth: return bwHit;
                case SqMode.Either: return kcHit || bwHit;
                default: return kcHit && bwHit;
            }
        }

        private static string HitLabel(bool kcHit, bool bwHit)
        {
            if (kcHit && bwHit) return "BOTH";
            if (kcHit) return "KC";
            if (bwHit) return "BW";
            return "";
        }

        private static string SafeFileName(string name)
        {
            foreach (char ch in Path.GetInvalidFileNameChars())
                name = name.Replace(ch, '_');
            return name;
        }

        private static string F3(double v)
        {
            return v.ToString("F3", Inv);
        }

        // MT5 と同じ表記（M15, H1, D1 …）にそろえる
        private static string TimeFrameLabel(TimeFrame tf)
        {
            if (tf == TimeFrame.Minute) return "M1";
            if (tf == TimeFrame.Minute2) return "M2";
            if (tf == TimeFrame.Minute3) return "M3";
            if (tf == TimeFrame.Minute4) return "M4";
            if (tf == TimeFrame.Minute5) return "M5";
            if (tf == TimeFrame.Minute10) return "M10";
            if (tf == TimeFrame.Minute15) return "M15";
            if (tf == TimeFrame.Minute20) return "M20";
            if (tf == TimeFrame.Minute30) return "M30";
            if (tf == TimeFrame.Minute45) return "M45";
            if (tf == TimeFrame.Hour) return "H1";
            if (tf == TimeFrame.Hour2) return "H2";
            if (tf == TimeFrame.Hour3) return "H3";
            if (tf == TimeFrame.Hour4) return "H4";
            if (tf == TimeFrame.Hour6) return "H6";
            if (tf == TimeFrame.Hour8) return "H8";
            if (tf == TimeFrame.Hour12) return "H12";
            if (tf == TimeFrame.Daily) return "D1";
            if (tf == TimeFrame.Weekly) return "W1";
            if (tf == TimeFrame.Monthly) return "MN1";
            return tf.ToString();
        }
    }
}
