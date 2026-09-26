//+------------------------------------------------------------------+
//| BBSqueezeAlert.mq5                                               |
//| BB スクイーズ・アラートインジケータ（MT5 カスタムインジケータ）  |
//| 仕様: docs/bb_alert_indicator_spec_v0_1.md（v0.1）               |
//|                                                                  |
//| - 判定は確定足のみ（rates_total-2 まで）。形成中の足は描画しない  |
//| - BB / EMA / ATR / BandWidth 分位はすべて自前計算                |
//| - 通知は SendNotification（スマホ push）のみ                     |
//|   prev_calculated==0 の一括計算中は通知しない（描画とログは行う）|
//| - ログ CSV は MQL5\Files\<Log_FileName>（空なら                   |
//|   bb_alert_log_<SYMBOL>_<TF>.csv）。一括計算時に作り直し、以後は  |
//|   追記。bar_time はサーバー時刻                                  |
//| - Dump_Bars=true なら一括計算の完了時に確定足の OHLC を           |
//|   bars_<SYMBOL>_<TF>.csv へ出力（bbsq_reference.py の入力）      |
//+------------------------------------------------------------------+
#property copyright "BB squeeze alert"
#property version   "0.10"
#property description "BB squeeze -> expansion breakout alert (spec v0.1)"
#property indicator_chart_window
#property indicator_buffers 16
#property indicator_plots   8

#property indicator_label1  "BB Upper"
#property indicator_type1   DRAW_LINE
#property indicator_color1  clrDodgerBlue
#property indicator_label2  "BB Mid"
#property indicator_type2   DRAW_LINE
#property indicator_color2  clrGray
#property indicator_style2  STYLE_DOT
#property indicator_label3  "BB Lower"
#property indicator_type3   DRAW_LINE
#property indicator_color3  clrDodgerBlue
#property indicator_label4  "KC Upper"
#property indicator_type4   DRAW_LINE
#property indicator_color4  clrOrange
#property indicator_style4  STYLE_DASH
#property indicator_label5  "KC Lower"
#property indicator_type5   DRAW_LINE
#property indicator_color5  clrOrange
#property indicator_style5  STYLE_DASH
#property indicator_label6  "Signal UP"
#property indicator_type6   DRAW_ARROW
#property indicator_color6  clrLime
#property indicator_width6  2
#property indicator_label7  "Signal DOWN"
#property indicator_type7   DRAW_ARROW
#property indicator_color7  clrRed
#property indicator_width7  2
#property indicator_label8  "Squeeze"
#property indicator_type8   DRAW_COLOR_ARROW
#property indicator_color8  clrSilver,clrDimGray
#property indicator_width8  1

enum ENUM_SQ_MODE
  {
   SQ_KELTNER   = 0, // Keltner
   SQ_BANDWIDTH = 1, // BandWidth
   SQ_EITHER    = 2, // Either
   SQ_BOTH      = 3  // Both
  };

enum ENUM_BREAK_MODE
  {
   BREAK_CLOSE = 0, // Close
   BREAK_BODY  = 1  // Body
  };

//---- 共通パラメータ（仕様 2 章。名前・型・既定値を cTrader 版と一致させる）
input int             BB_Period     = 20;
input double          BB_Dev        = 2.0;
input int             KC_Period     = 20;
input int             KC_AtrPeriod  = 20;
input double          KC_Mult       = 1.5;
input ENUM_SQ_MODE    Sq_Mode       = SQ_EITHER;
input int             Sq_MinBars    = 6;
input int             Sq_BwLookback = 120;
input double          Sq_BwPct      = 20.0;
input ENUM_BREAK_MODE Break_Mode    = BREAK_CLOSE;
input bool            Alert_Enabled = true;
input bool            Log_Enabled   = true;
input string          Log_FileName  = "";
input bool            Dump_Bars     = false;
//---- 実装固有パラメータ（判定には関与しない）
input bool            Show_Keltner  = false;

//---- 描画バッファ
double BufUpper[];
double BufMid[];
double BufLower[];
double BufKcUp[];
double BufKcLo[];
double BufArrUp[];
double BufArrDn[];
double BufSqDot[];
double BufSqColor[];
//---- 内部計算バッファ
double CalcEma[];
double CalcAtr[];
double CalcBw[];
double CalcBwPct[];
double CalcKcHit[];
double CalcBwHit[];
double CalcSqLen[];

int      g_processed    = -1;   // 評価済みの最後の確定足
int      g_warm         = 0;    // 判定を始める最初の足
datetime g_lastAlertBar = 0;
string   g_tf           = "";
bool     g_warnedNotify = false;
string   g_logName      = "";

#define CSV_HEADER "platform,symbol,tf,bar_time,dir,open,close,upper,lower,mid,bw_pct,kc_up,kc_lo,sqlen,sq_mode_hit"

//+------------------------------------------------------------------+
int OnInit()
  {
   if(BB_Period < 2 || KC_Period < 1 || KC_AtrPeriod < 1 || Sq_BwLookback < 1 ||
      Sq_MinBars < 1 || BB_Dev <= 0.0 || KC_Mult <= 0.0)
     {
      Print("BBSQ: invalid parameters");
      return(INIT_PARAMETERS_INCORRECT);
     }

   SetIndexBuffer(0, BufUpper,   INDICATOR_DATA);
   SetIndexBuffer(1, BufMid,     INDICATOR_DATA);
   SetIndexBuffer(2, BufLower,   INDICATOR_DATA);
   SetIndexBuffer(3, BufKcUp,    INDICATOR_DATA);
   SetIndexBuffer(4, BufKcLo,    INDICATOR_DATA);
   SetIndexBuffer(5, BufArrUp,   INDICATOR_DATA);
   SetIndexBuffer(6, BufArrDn,   INDICATOR_DATA);
   SetIndexBuffer(7, BufSqDot,   INDICATOR_DATA);
   SetIndexBuffer(8, BufSqColor, INDICATOR_COLOR_INDEX);
   SetIndexBuffer(9,  CalcEma,   INDICATOR_CALCULATIONS);
   SetIndexBuffer(10, CalcAtr,   INDICATOR_CALCULATIONS);
   SetIndexBuffer(11, CalcBw,    INDICATOR_CALCULATIONS);
   SetIndexBuffer(12, CalcBwPct, INDICATOR_CALCULATIONS);
   SetIndexBuffer(13, CalcKcHit, INDICATOR_CALCULATIONS);
   SetIndexBuffer(14, CalcBwHit, INDICATOR_CALCULATIONS);
   SetIndexBuffer(15, CalcSqLen, INDICATOR_CALCULATIONS);

   for(int pl = 0; pl < 8; pl++)
      PlotIndexSetDouble(pl, PLOT_EMPTY_VALUE, EMPTY_VALUE);

   PlotIndexSetInteger(5, PLOT_ARROW, 233);
   PlotIndexSetInteger(6, PLOT_ARROW, 234);
   PlotIndexSetInteger(7, PLOT_ARROW, 159);

   if(!Show_Keltner)
     {
      PlotIndexSetInteger(3, PLOT_DRAW_TYPE, DRAW_NONE);
      PlotIndexSetInteger(4, PLOT_DRAW_TYPE, DRAW_NONE);
     }

   g_warm = MathMax(BB_Period + Sq_BwLookback, MathMax(KC_Period, KC_AtrPeriod));
   g_tf = StringSubstr(EnumToString((ENUM_TIMEFRAMES)_Period), 7); // "PERIOD_M15" -> "M15"
   g_processed = -1;
   string logName = Log_FileName;
   StringTrimLeft(logName);
   StringTrimRight(logName);
   if(logName == "")
      logName = "bb_alert_log_" + _Symbol + "_" + g_tf + ".csv";
   g_logName = SafeFileName(logName);

   IndicatorSetString(INDICATOR_SHORTNAME, "BBSQ(" + (string)BB_Period + "," + DoubleToString(BB_Dev, 1) + ")");
   IndicatorSetInteger(INDICATOR_DIGITS, _Digits);
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
  {
   if(rates_total < 2)
      return(0);

   // 過去 -> 現在の順（0 が最古）で扱う
   ArraySetAsSeries(time, false);
   ArraySetAsSeries(open, false);
   ArraySetAsSeries(high, false);
   ArraySetAsSeries(low, false);
   ArraySetAsSeries(close, false);

   bool initial = (prev_calculated == 0 || g_processed >= rates_total - 1);
   if(initial)
     {
      // チャート再読込・パラメータ変更・履歴更新: 描画とログを作り直し、通知は出さない
      g_processed = -1;
      ClearPlots(0, rates_total - 1);
      if(Log_Enabled)
         LogReset();
     }

   int lastClosed = rates_total - 2;
   while(g_processed < lastClosed)
     {
      g_processed++;
      Process(g_processed, !initial, time, open, high, low, close);
     }

   if(initial && Dump_Bars)
      DumpBars(lastClosed, time, open, high, low, close);

   // 形成中の足は描画しない
   ClearPlots(rates_total - 1, rates_total - 1);
   return(rates_total);
  }

//+------------------------------------------------------------------+
void Process(const int i, const bool notify,
             const datetime &time[], const double &open[], const double &high[],
             const double &low[], const double &close[])
  {
   int n = BB_Period, q = KC_Period, p = KC_AtrPeriod, lb = Sq_BwLookback;

   //---- ボリンジャーバンド（母集団標準偏差）
   bool bbOk = (i >= n - 1);
   double mid = EMPTY_VALUE, upper = EMPTY_VALUE, lower = EMPTY_VALUE, bw = EMPTY_VALUE;
   if(bbOk)
     {
      double sum = 0.0;
      for(int k = 0; k < n; k++)
         sum += close[i - k];
      mid = sum / n;
      double sumSq = 0.0;
      for(int k = 0; k < n; k++)
        {
         double d = close[i - k] - mid;
         sumSq += d * d;
        }
      double sd = MathSqrt(sumSq / n);
      upper = mid + BB_Dev * sd;
      lower = mid - BB_Dev * sd;
      bw = (upper - lower) / mid;
     }
   CalcBw[i] = bw;

   //---- EMA（初期値は最初の q 本の SMA）
   double ema = EMPTY_VALUE;
   if(i == q - 1)
     {
      double sum = 0.0;
      for(int k = 0; k < q; k++)
         sum += close[i - k];
      ema = sum / q;
     }
   else if(i >= q)
     {
      double alpha = 2.0 / (q + 1);
      ema = CalcEma[i - 1] + alpha * (close[i] - CalcEma[i - 1]);
     }
   CalcEma[i] = ema;

   //---- ATR（Wilder。TR_0 = High_0 - Low_0、初期値は最初の p 本の TR 平均）
   double atr = EMPTY_VALUE;
   if(i == p - 1)
     {
      double sum = 0.0;
      for(int k = 0; k < p; k++)
         sum += TrueRange(i - k, high, low, close);
      atr = sum / p;
     }
   else if(i >= p)
      atr = ((p - 1) * CalcAtr[i - 1] + TrueRange(i, high, low, close)) / p;
   CalcAtr[i] = atr;

   bool kcOk = (i >= q - 1 && i >= p - 1);
   double kcUp = kcOk ? ema + KC_Mult * atr : EMPTY_VALUE;
   double kcLo = kcOk ? ema - KC_Mult * atr : EMPTY_VALUE;

   //---- BandWidth 分位（足 i を含む直近 lb 本で BW_i 以下の本数 / lb）
   double bwPct = EMPTY_VALUE;
   if(i >= n - 1 + lb - 1)
     {
      int cnt = 0;
      for(int k = 0; k < lb; k++)
         if(CalcBw[i - k] <= bw)
            cnt++;
      bwPct = cnt * 100.0 / lb;
     }
   CalcBwPct[i] = bwPct;

   //---- スクイーズ状態 / 継続本数
   bool kcHit = false, bwHit = false, sq = false;
   if(i >= g_warm)
     {
      kcHit = (upper <= kcUp && lower >= kcLo);
      bwHit = (bwPct <= Sq_BwPct);
      sq = IsSqueeze(kcHit, bwHit);
     }
   CalcKcHit[i] = kcHit ? 1.0 : 0.0;
   CalcBwHit[i] = bwHit ? 1.0 : 0.0;
   int prevLen = (i > 0) ? (int)CalcSqLen[i - 1] : 0;
   int sqLen = sq ? prevLen + 1 : 0;
   CalcSqLen[i] = sqLen;

   //---- 描画（確定足のみ）
   BufUpper[i] = upper;
   BufMid[i]   = mid;
   BufLower[i] = lower;
   BufKcUp[i]  = kcUp;
   BufKcLo[i]  = kcLo;
   BufArrUp[i] = EMPTY_VALUE;
   BufArrDn[i] = EMPTY_VALUE;
   if(sq)
     {
      BufSqDot[i]   = lower - 0.5 * atr;
      BufSqColor[i] = (sqLen >= Sq_MinBars) ? 1.0 : 0.0;
     }
   else
     {
      BufSqDot[i]   = EMPTY_VALUE;
      BufSqColor[i] = 0.0;
     }

   //---- 発火判定（足 i 自身のバンドで判定）
   if(i <= g_warm || sq || prevLen < Sq_MinBars)
      return;

   double o = open[i], c = close[i];
   string dir = "";
   if(Break_Mode == BREAK_CLOSE)
     {
      if(c > upper)
         dir = "UP";
      else if(c < lower)
         dir = "DOWN";
     }
   else
     {
      if(MathMin(o, c) > upper)
         dir = "UP";
      else if(MathMax(o, c) < lower)
         dir = "DOWN";
     }
   if(dir == "")
      return; // 解除したが発火なし（この解除は消費済み）

   datetime t = time[i];
   string hit = HitLabel(CalcKcHit[i - 1] > 0.5, CalcBwHit[i - 1] > 0.5);

   //---- 矢印
   if(dir == "UP")
      BufArrUp[i] = high[i] + 0.3 * atr;
   else
      BufArrDn[i] = low[i] - 0.3 * atr;

   //---- ログ（過去足も書く）
   if(Log_Enabled)
     {
      string row = "MT5," + _Symbol + "," + g_tf + "," + BarTime(t) + "," + dir + "," +
                   F3(o) + "," + F3(c) + "," + F3(upper) + "," + F3(lower) + "," + F3(mid) + "," +
                   DoubleToString(bwPct, 1) + "," + F3(kcUp) + "," + F3(kcLo) + "," +
                   IntegerToString(prevLen) + "," + hit;
      LogAppend(row);
     }

   //---- 通知（一括計算中は出さない。同じ足では 1 回だけ）
   if(!notify || !Alert_Enabled || t == g_lastAlertBar)
      return;
   g_lastAlertBar = t;

   string msg = "BBSQ " + _Symbol + " " + g_tf + " " + dir + " " + BarTime(t) +
                " close=" + F3(c) + " " + (dir == "UP" ? "upper=" + F3(upper) : "lower=" + F3(lower)) +
                " sqlen=" + IntegerToString(prevLen);
   Print(msg);
   if(!TerminalInfoInteger(TERMINAL_NOTIFICATIONS_ENABLED))
     {
      if(!g_warnedNotify)
         Print("BBSQ: push notifications are disabled (Tools > Options > Notifications)");
      g_warnedNotify = true;
      return;
     }
   if(!SendNotification(msg))
      Print("BBSQ: SendNotification failed, error ", GetLastError());
  }

//+------------------------------------------------------------------+
double TrueRange(const int i, const double &high[], const double &low[], const double &close[])
  {
   double h = high[i], l = low[i];
   if(i == 0)
      return(h - l);
   double pc = close[i - 1];
   return(MathMax(h - l, MathMax(MathAbs(h - pc), MathAbs(l - pc))));
  }

bool IsSqueeze(const bool kcHit, const bool bwHit)
  {
   switch(Sq_Mode)
     {
      case SQ_KELTNER:
         return(kcHit);
      case SQ_BANDWIDTH:
         return(bwHit);
      case SQ_EITHER:
         return(kcHit || bwHit);
      default:
         return(kcHit && bwHit);
     }
  }

string HitLabel(const bool kcHit, const bool bwHit)
  {
   if(kcHit && bwHit)
      return("BOTH");
   if(kcHit)
      return("KC");
   if(bwHit)
      return("BW");
   return("");
  }

string SafeFileName(string name)
  {
   string bad = "\\/:*?\"<>|";
   for(int k = 0; k < StringLen(bad); k++)
      StringReplace(name, StringSubstr(bad, k, 1), "_");
   return(name);
  }

//---- 確定足 0..lastClosed の OHLC を bbsq_reference.py の入力形式で書き出す
void DumpBars(const int lastClosed, const datetime &time[], const double &open[],
              const double &high[], const double &low[], const double &close[])
  {
   string name = SafeFileName("bars_" + _Symbol + "_" + g_tf + ".csv");
   int h = FileOpen(name, FILE_WRITE | FILE_BIN | FILE_SHARE_READ);
   if(h == INVALID_HANDLE)
     {
      Print("BBSQ: bar dump failed, error ", GetLastError());
      return;
     }
   WriteLine(h, "time,open,high,low,close");
   for(int i = 0; i <= lastClosed; i++)
      WriteLine(h, BarTime(time[i]) + "," + DoubleToString(open[i], _Digits) + "," +
                DoubleToString(high[i], _Digits) + "," + DoubleToString(low[i], _Digits) + "," +
                DoubleToString(close[i], _Digits));
   FileClose(h);
   PrintFormat("BBSQ: dumped %d bars to %s", lastClosed + 1, name);
  }

string F3(const double v)
  {
   return(DoubleToString(v, 3));
  }

// "YYYY-MM-DD HH:MM"（サーバー時刻）
string BarTime(const datetime t)
  {
   string s = TimeToString(t, TIME_DATE | TIME_MINUTES); // "YYYY.MM.DD HH:MM"
   StringReplace(s, ".", "-");
   return(s);
  }

void ClearPlots(const int from, const int to)
  {
   for(int i = from; i <= to; i++)
     {
      BufUpper[i] = EMPTY_VALUE;
      BufMid[i]   = EMPTY_VALUE;
      BufLower[i] = EMPTY_VALUE;
      BufKcUp[i]  = EMPTY_VALUE;
      BufKcLo[i]  = EMPTY_VALUE;
      BufArrUp[i] = EMPTY_VALUE;
      BufArrDn[i] = EMPTY_VALUE;
      BufSqDot[i] = EMPTY_VALUE;
      BufSqColor[i] = 0.0;
     }
  }

//---- ログ CSV（改行は CRLF、UTF-8。バイナリで書いて改行コードを固定する）
void WriteLine(const int h, const string line)
  {
   uchar buf[];
   int len = StringToCharArray(line + "\r\n", buf, 0, WHOLE_ARRAY, CP_UTF8) - 1; // 終端 NUL を除く
   if(len > 0 && FileWriteArray(h, buf, 0, len) != (uint)len)
      Print("BBSQ: file write failed, error ", GetLastError());
  }

void LogReset()
  {
   int h = FileOpen(g_logName, FILE_WRITE | FILE_BIN | FILE_SHARE_READ);
   if(h == INVALID_HANDLE)
     {
      Print("BBSQ: log file init failed, error ", GetLastError());
      return;
     }
   WriteLine(h, CSV_HEADER);
   FileClose(h);
  }

void LogAppend(const string row)
  {
   int h = FileOpen(g_logName, FILE_READ | FILE_WRITE | FILE_BIN | FILE_SHARE_READ);
   if(h == INVALID_HANDLE)
     {
      Print("BBSQ: log write failed, error ", GetLastError());
      return;
     }
   if(!FileSeek(h, 0, SEEK_END))
      Print("BBSQ: file seek failed, error ", GetLastError());
   WriteLine(h, row);
   FileClose(h);
  }
//+------------------------------------------------------------------+
