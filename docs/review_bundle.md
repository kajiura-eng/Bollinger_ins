# BBスクイーズ・アラートインジケータ レビュー依頼パッケージ

このファイル 1 本に、仕様書・実装コード・設計判断・既知の論点をすべてまとめています。前提知識なしでレビューできます。

- リポジトリ: kajiura-eng/Bollinger_ins（ブランチ `claude/new-session-m1za20`）
- 状態: 仕様書 v0.1 に基づく初版実装。C# / MQL5 はコンパイル未確認（コンパイラのない環境で作成）。Python リファレンス実装のテスト 14 件は成功

## レビューしてほしいこと

以下の観点で、**問題のある箇所を「ファイル名:該当コード」と具体的な失敗例つき**で指摘してください。問題がない観点は「問題なし」と明記してください。

1. **仕様との一致**: 3 実装（cTrader C# / MQL5 / Python）が仕様書 3〜7 章の式・判定・確定足ルールどおりか。特に 4.3 発火条件、4.4 バンド参照足、5 章の通知抑止
2. **3 実装間の一致**: 同じ OHLC を与えたとき 3 つが同じ足・同じ方向で発火し、同じ CSV 行を出すか。計算順・初期値・境界条件（`<` と `<=`、warm-up の境界）の食い違いがないか
3. **コンパイル・実行時エラー**: cTrader Automate API / MQL5 の API の誤用、型エラー、存在しないメンバー、配列範囲外参照
4. **確定足と通知**: 形成中の足を判定・描画していないか。初回ロード・再計算・新しい足の生成時に、通知が「出るべき時に 1 回だけ」出るか
5. **ログ CSV**: 起動時の作り直しと追記、フォーマット（小数桁、時刻形式、改行）が両実装で一致するか
6. **下記「実装で決めたこと」「仕様書への指摘」の妥当性**: 反対意見があれば理由つきで

## 構成

| ファイル | 内容 |
| --- | --- |
| `docs/bb_alert_indicator_spec_v0_1.md` | 仕様書 v0.1（唯一の正） |
| `ctrader/BBSqueezeAlert.cs` | cTrader Automate C# Indicator |
| `mt5/BBSqueezeAlert.mq5` | MQL5 カスタムインジケータ |
| `tools/bbsq_reference.py` | Python リファレンス実装（同形式のログ CSV を出す） |
| `tools/compare_logs.py` | 2 つのログ CSV の突き合わせ（仕様 8 章） |
| `tests/test_reference.py` | Python 実装と突き合わせツールのテスト |

## 実装で決めたこと（仕様書に明記がない箇所）

1. **判定開始足**: 8 章「Sq_BwLookback + BB_Period 本以降のみ判定」を、足インデックス（0 始まり）≥ `max(BB_Period + Sq_BwLookback, KC_Period, KC_AtrPeriod)` と解釈。それより前は Sq=false、SqLen=0。発火は足 i-1 が判定開始足以降（i > warm）のときのみ
2. **最初の TR**: TR_0 = High_0 − Low_0。ATR 初期値は足 0〜p−1 の TR 平均を足 p−1 に置く。EMA は足 q−1 に最初の q 本の SMA
3. **合計の順序**: SMA・分散は k = 0..n−1（新しい足から古い足へ）の順で合計し、3 実装で浮動小数点の丸めをそろえる
4. **sqlen / sq_mode_hit**: `sqlen` は解除直前足の SqLen。`sq_mode_hit` は Sq_Mode に関係なく、解除直前足で実際に成立していた条件（KC / BW / BOTH）
5. **スクイーズ帯の描画（未決事項）**: 暫定で下バンドの 0.5×ATR 下に点列。SqLen < Sq_MinBars は薄い色、SqLen ≥ Sq_MinBars に達した足から濃い色（遡って塗り直さない）
6. **追加パラメータ（判定に関与しない）**: 両実装に `Show_Keltner`（既定 false）、cTrader に `Sound_File`
7. **時刻**: cTrader にはサーバー時刻がないため UTC で出力。MT5 はサーバー時刻。突き合わせは `compare_logs.py` の `--ctrader-tz` / `--mt5-tz`（IANA 名、例: Europe/Athens）で UTC にそろえる
8. **価格桁**: 仕様どおり小数 3 桁固定（GBPJPY 前提）
9. **ログ**: UTF-8（BOM なし）、CRLF。MQL5 は改行コードを固定するためバイナリで書き込む
10. **通知の判定**: cTrader は `IsLastBar` に初めて到達するまでを初回ロードとみなす。MT5 は `prev_calculated == 0` の呼び出しを初回ロード・再計算とみなし、ログも作り直す
11. **パラメータ下限**: Sq_MinBars ≥ 1、BB_Period ≥ 2 など（MT5 は OnInit で INIT_PARAMETERS_INCORRECT）

## 仕様書への指摘（作成者の見解）

- **3 章「MT5 の iATR と同一」は誤り**: MT5 標準 ATR は TR の単純移動平均で Wilder 平滑ではない。実装は両方とも仕様の式（Wilder）で自前計算しているので一致には影響しないが、記述の修正が必要
- **BW 分位の同値**: 「BW_i 以下の本数」なので同値の BW が並ぶと分位が高く出る（スクイーズ判定されにくい）
- **EMA / ATR の起点依存**: 再帰計算のため履歴の開始位置で初期の値がずれる。比較期間は両方の履歴の先頭から十分後ろに置く必要がある
- **再接続時の通知**: 複数の足をまとめて評価したときは足ごとに通知が出る（同じ足の重複はない）
- **BB_Period が小さいと抜けない**: 母集団σでは外れ値 1 本の z は最大 (n−1)/√n。n ≤ 5 では 2σ を超えられない（既定値 20 では問題なし）

---

## `docs/bb_alert_indicator_spec_v0_1.md`

````markdown
# BBスクイーズ・アラートインジケータ 共通仕様書 v0.1

Sep 26, 2026 · @TOSHIKI

## 1. 目的とスコープ

GBPJPY M15 で、ボリンジャーバンドがスクイーズからエクスパンションに切り替わった直後の足が終値で2σ線を抜けたとき、cTrader 版と MT5 版が**同じ足で同じ方向**に発火する裁量補助インジケータを2本作る。両口座で裁量比較を行うため、判定ロジックは本書を唯一の正とし、両実装は本書から独立に書き起こす。

- 検出ロジックは [[bb-squeeze-ea]] v2（cBot）の Sq_Mode=Either を流用する
- エントリー・イグジット・ポジション管理は含まない（アラートと描画・ログのみ）
- 対象: GBPJPY M15。他通貨・他時間足はパラメータで対応可能とするが検証対象外
- cTrader 版は cTrader Automate C# Indicator、MT5 版は MQL5 カスタムインジケータ

## 2. 共通パラメータ

名前・型・既定値を両実装で一致させる。Sq_MinBars と Sq_BwPct の既定値は v2 と同じ暫定値で、Claude Code に依頼中のスクイーズ継続本数ヒストグラム分析の結果で差し替える。

| パラメータ | 型 | 既定値 | 意味 |
| --- | --- | --- | --- |
| BB_Period | int | 20 | BB の期間（終値 SMA） |
| BB_Dev | double | 2.0 | BB の標準偏差倍率 |
| KC_Period | int | 20 | Keltner 中心線 EMA の期間 |
| KC_AtrPeriod | int | 20 | Keltner 用 ATR の期間 |
| KC_Mult | double | 1.5 | Keltner 幅 = ATR × KC_Mult |
| Sq_Mode | enum | Either | Keltner / BandWidth / Either / Both |
| Sq_MinBars | int | 6 | スクイーズとみなす最小継続本数 |
| Sq_BwLookback | int | 120 | BandWidth パーセンタイルの参照本数 |
| Sq_BwPct | double | 20.0 | BandWidth がこの分位以下ならスクイーズ（%） |
| Break_Mode | enum | Close | Close = 終値がバンド外 / Body = 始値・終値ともバンド外 |
| Alert_Enabled | bool | true | 通知の ON/OFF |
| Log_Enabled | bool | true | CSV ログ出力の ON/OFF |
| Log_FileName | string | bb_alert_log.csv | ログファイル名 |

実装固有のパラメータ（MT5 の SendNotification 用ID、cTrader の音ファイル）は各実装で追加してよいが、判定に関わるパラメータは本表以外に置かない。

## 3. 計算定義

両プラットフォームの組込指標は実装差があるため、**すべて自前計算**とし、下式を両実装で同一にする。添字 i は足番号、Close[i] 等は確定足の値。

**ボリンジャーバンド**（標準偏差は母集団方式、n で割る）

```latex
Mid_i = \frac{1}{n}\sum_{k=0}^{n-1} Close_{i-k},\quad
\sigma_i = \sqrt{\frac{1}{n}\sum_{k=0}^{n-1}(Close_{i-k}-Mid_i)^2}
```

```latex
Upper_i = Mid_i + d\,\sigma_i,\quad Lower_i = Mid_i - d\,\sigma_i
```

n = BB_Period、d = BB_Dev。

**ATR**（Wilder 方式。MT5 の iATR と同一、cTrader 側もこの式で自前計算する）

```latex
TR_i = \max(High_i-Low_i,\ |High_i-Close_{i-1}|,\ |Low_i-Close_{i-1}|),\quad
ATR_i = \frac{(p-1)\,ATR_{i-1}+TR_i}{p}
```

p = KC_AtrPeriod。初期値 ATR は最初の p 本の TR 単純平均。

**Keltner チャネル**

```latex
KC_{mid,i} = EMA_{q}(Close)_i,\quad KC_{up,i} = KC_{mid,i} + m\,ATR_i,\quad KC_{lo,i} = KC_{mid,i} - m\,ATR_i
```

q = KC_Period、m = KC_Mult。EMA の平滑係数は 2/(q+1)、初期値は最初の q 本の SMA。

**BandWidth と分位**

```latex
BW_i = \frac{Upper_i - Lower_i}{Mid_i}
```

BW パーセンタイル = 直近 Sq_BwLookback 本（足 i を含む）の BW を昇順に並べたとき、BW_i 以下の本数を Sq_BwLookback で割った値（%）。順位 1 位なら 1/Sq_BwLookback×100。補間はしない。

## 4. 判定ロジック

発火は「解除した足そのもの」1本だけを見る。解除の1本後・2本後は対象外（それは v2 のバンドウォークであり本インジケータの範囲外）。

**4.1 スクイーズ状態 Sq[i]**（足ごとに true/false）

- KC 条件: Upper_i ≤ KC_up,i かつ Lower_i ≥ KC_lo,i（BB が Keltner に内包）
- BW 条件: BW パーセンタイル_i ≤ Sq_BwPct
- Sq_Mode により Keltner=KC条件のみ、BandWidth=BW条件のみ、Either=どちらか、Both=両方

**4.2 スクイーズ継続本数 SqLen[i]**

- Sq[i] が true なら SqLen[i] = SqLen[i-1] + 1、false なら 0

**4.3 発火条件（足 i で評価）**

次の3つが同時に成立したとき、足 i でシグナル。

1. SqLen[i-1] ≥ Sq_MinBars（直前足まで有効なスクイーズが続いていた）
2. Sq[i] = false（足 i でスクイーズ解除）
3. 突破判定
   - Break_Mode=Close: Close_i > Upper_i → 上、Close_i < Lower_i → 下
   - Break_Mode=Body: 上は min(Open_i, Close_i) > Upper_i、下は max(Open_i, Close_i) < Lower_i

条件 3 で上下いずれにも該当しなければ、解除はしたが発火なし。この場合その解除は消費済みとし、次に SqLen が再び Sq_MinBars に達するまで発火しない（4.2 の定義で自動的に満たされる）。

**4.4 バンド値の参照足**

条件 3 の Upper_i / Lower_i は足 i 自身の確定値を使う。足 i-1 のバンドを使う案は採らない（足 i の大陽線・大陰線でバンド自体が広がるため、i-1 基準では発火しやすくなりすぎる）。

## 5. 確定足ルールと通知の抑止

判定は**確定足のみ**。形成中の足では一切判定・描画・通知しない（EA 検証で確定足のみ判定が支持されている）。

| 項目 | 共通ルール | cTrader 実装 | MT5 実装 |
| --- | --- | --- | --- |
| 評価対象 | 直近確定足 = 形成中の足の1本前 | Calculate(index) で index が最終足なら index-1 を評価 | OnCalculate で rates_total-2 を評価（rates_total-1 は形成中） |
| 二重通知防止 | 発火足の開始時刻を保持し、同じ時刻なら再通知しない | DateTime lastAlertBar | datetime lastAlertBar（time[] を保持） |
| 初回ロード抑止 | インジケータ起動時に過去足で通知しない。描画とログは過去足にも行う | 起動時刻より古い足では Notify を呼ばない（IsLastBar 判定） | prev_calculated==0 の一括計算中は通知しない |
| 再計算 | チャート再読込・パラメータ変更で過去シグナルの描画は再生成、通知は出さない | 同上 | 同上 |

通知は「新しい確定足が生成された瞬間」に1回だけ出る。過去ログとの突き合わせは 7 章の CSV で行う。

## 6. 通知仕様

cTrader 版はチャート内アラートのみ、MT5 版はスマホへのプッシュ通知のみ。メールは両方とも使わない。

| 項目 | cTrader 版 | MT5 版 |
| --- | --- | --- |
| 手段 | Notifications.PlaySound + チャート上テキスト | SendNotification |
| 事前設定 | 音ファイルのパス（パラメータ） | ツール→オプション→通知で MetaQuotes ID を登録、通知を有効化 |
| メッセージ | 表示のみ（下記フォーマット） | 同フォーマットを本文に |
| 未使用 | SendEmail, Http | SendMail, Alert, WebRequest |

**メッセージフォーマット**（両実装共通、1行）

```
BBSQ GBPJPY M15 DOWN 2026-09-22 16:30 close=210.438 lower=210.463 sqlen=8
```

方向は UP / DOWN、時刻は足の開始時刻（サーバー時刻）。sqlen は解除直前の SqLen。MT5 の SendNotification は 255 文字制限があるので、このフォーマットに収める。

## 7. チャート描画とログ

**描画**（過去足も含めて再現する）

- 発火足の高値上（UP）または安値下（DOWN）に矢印。UP は上向き、DOWN は下向き
- スクイーズ継続中（Sq[i]=true）の足に薄い背景帯、または下部に点列。SqLen ≥ Sq_MinBars の区間だけ色を濃くする
- BB 上下バンドと Mid は描画する（標準の BB は重ねない。自前計算値と一致確認のため）
- Keltner チャネルは既定で非表示、パラメータで表示可

**ログ CSV**（発火ごとに 1 行追記。突き合わせの主データ）

```csv
platform,symbol,tf,bar_time,dir,open,close,upper,lower,mid,bw_pct,kc_up,kc_lo,sqlen,sq_mode_hit
cTrader,GBPJPY,M15,2026-09-22 16:30,DOWN,210.552,210.438,210.789,210.463,210.626,12.5,210.801,210.451,8,KC
```

- bar_time は足の開始時刻（サーバー時刻、YYYY-MM-DD HH:MM）
- 価格は小数 3 桁、bw_pct は小数 1 桁
- sq_mode_hit は解除直前足で成立していた条件（KC / BW / BOTH）
- 保存先: cTrader は Documents\\cAlgo\\Data 配下、MT5 は MQL5\\Files 配下。ファイル名は Log_FileName
- 初回ロード時の過去足シグナルも同じ形式で書き出す（過去分の突き合わせに使う）。重複防止のため、起動時は過去足分でファイルを作り直し（上書き）、以後の新規シグナルのみ追記する。突き合わせ用に残したい場合は起動前にファイルを退避する

## 8. プラットフォーム差異と一致確認

計算式を揃えても、データとサーバー時刻の違いで完全一致はしない。許容範囲を先に決めておく。

| 差異の源 | 影響 | 対処 |
| --- | --- | --- |
| ブローカーの価格データ（Bid ベース、フィード差） | Close が 0.1〜0.5 pips ずれ、バンド際の足で発火有無が分かれる | 許容。不一致足はログで理由（close と upper/lower の差）を記録して裁量比較の注記にする |
| サーバー時刻の GMT オフセット | bar_time がずれる | 突き合わせ時にオフセットを補正。M15 の足境界は 15 分単位なので判定自体は影響なし |
| 週明け・祝日のギャップ足 | 両者で足数が違うと SqLen がずれる | 日足境界ではなく足数で計算しているので、欠損足がある側は SqLen が短くなる。発火不一致の主要因候補として記録 |
| 過去足の本数 | パーセンタイルの参照窓の起点がずれる | 初回ロード時は Sq_BwLookback + BB_Period 本以降のみ判定。両者とも同じ日付から開始 |

**一致確認手順**

1. 両実装を同一チャート（GBPJPY M15）に適用し、同じ日付範囲でログ CSV を出力
2. bar_time（オフセット補正後）と dir で突き合わせ、一致 / cTrader のみ / MT5 のみ に分類
3. 片側のみの足は close と upper/lower の差を見て「価格差」か「SqLen 差」かを判定
4. 直近 3 ヶ月で一致率 90% 以上なら裁量比較に使用開始。下回れば差異要因を本書に追記して式を再検討

## 9. 未決事項

- [ ] Sq_MinBars と Sq_BwPct の既定値をヒストグラム分析の結果で確定する
- [ ] Break_Mode の既定値を Close にするか Body にするか（本書は Close を仮置き）
- [ ] スクイーズ帯の描画方式（背景帯 / 点列）を決める
- [ ] 一致率の合格ライン 90% の妥当性
- [ ] 実装順: cTrader 版（v2 cBot から流用）→ MT5 版（mql5-code-generation で生成）→ 一致確認
````

## `ctrader/BBSqueezeAlert.cs`

````csharp
// BB スクイーズ・アラートインジケータ（cTrader Automate C# Indicator）
// 仕様: docs/bb_alert_indicator_spec_v0_1.md（v0.1）。判定ロジックは仕様書が唯一の正。
//
// - 判定は確定足のみ。Calculate(index) で index-1（直近確定足）までを 1 回ずつ評価する
// - BB / EMA / ATR / BandWidth 分位はすべて自前計算（組込指標は使わない）
// - 通知はチャート内テキスト + 音のみ。起動時の過去足では通知しない（描画とログは行う）
// - ログ CSV は Documents\cAlgo\Data\<Log_FileName>。起動時に作り直し、以後は追記
// - 足の時刻は UTC（TimeZone = TimeZones.UTC）。MT5 ログとの突き合わせは tools/compare_logs.py で補正する

using System;
using System.Globalization;
using System.IO;
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

        [Parameter("Log_FileName", DefaultValue = "bb_alert_log.csv", Group = "Output")]
        public string Log_FileName { get; set; }

        // ---- 実装固有パラメータ（判定には関与しない） ----
        [Parameter("Sound_File", DefaultValue = "", Group = "Output")]
        public string Sound_File { get; set; }

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
        private string _logPath;
        private string _tf;

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

            if (Log_Enabled)
            {
                try
                {
                    string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "cAlgo", "Data");
                    Directory.CreateDirectory(dir);
                    _logPath = Path.Combine(dir, Log_FileName);
                    // 起動時は作り直す（過去足分をこの後書き出す）
                    File.WriteAllText(_logPath, CsvHeader + Environment.NewLine, new UTF8Encoding(false));
                }
                catch (Exception ex)
                {
                    Print("BBSQ: log file init failed: " + ex.Message);
                    _logPath = null;
                }
            }
        }

        public override void Calculate(int index)
        {
            // 形成中の足（index）は判定・描画しない。index-1 までの確定足を 1 本ずつ評価する
            int lastClosed = index - 1;
            while (_processed < lastClosed)
            {
                _processed++;
                Process(_processed);
            }

            // 最終足に到達した時点で初回ロード完了。以後に確定した足だけ通知する
            if (IsLastBar)
                _live = true;
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
                Chart.DrawIcon("BBSQ_" + t.Ticks, ChartIconType.UpArrow, t, Bars.HighPrices[i] + 0.3 * atr, Color.LimeGreen);
            else
                Chart.DrawIcon("BBSQ_" + t.Ticks, ChartIconType.DownArrow, t, Bars.LowPrices[i] - 0.3 * atr, Color.Red);

            // ログ（過去足も書く）
            if (_logPath != null)
            {
                string row = string.Join(",",
                    "cTrader", SymbolName, _tf, t.ToString("yyyy-MM-dd HH:mm", Inv), dir,
                    F3(o), F3(c), F3(upper), F3(lower), F3(mid), bwPct.ToString("F1", Inv),
                    F3(kcUp), F3(kcLo), prevLen.ToString(Inv), hit);
                try
                {
                    File.AppendAllText(_logPath, row + Environment.NewLine, new UTF8Encoding(false));
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
            Chart.DrawStaticText("BBSQ_msg", msg, VerticalAlignment.Top, HorizontalAlignment.Left,
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
````

## `mt5/BBSqueezeAlert.mq5`

````cpp
//+------------------------------------------------------------------+
//| BBSqueezeAlert.mq5                                               |
//| BB スクイーズ・アラートインジケータ（MT5 カスタムインジケータ）  |
//| 仕様: docs/bb_alert_indicator_spec_v0_1.md（v0.1）               |
//|                                                                  |
//| - 判定は確定足のみ（rates_total-2 まで）。形成中の足は描画しない  |
//| - BB / EMA / ATR / BandWidth 分位はすべて自前計算                |
//| - 通知は SendNotification（スマホ push）のみ                     |
//|   prev_calculated==0 の一括計算中は通知しない（描画とログは行う）|
//| - ログ CSV は MQL5\Files\<Log_FileName>。一括計算時に作り直し、  |
//|   以後は追記。bar_time はサーバー時刻                            |
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
input string          Log_FileName  = "bb_alert_log.csv";
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
   if(len > 0)
      FileWriteArray(h, buf, 0, len);
  }

void LogReset()
  {
   int h = FileOpen(Log_FileName, FILE_WRITE | FILE_BIN | FILE_SHARE_READ);
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
   int h = FileOpen(Log_FileName, FILE_READ | FILE_WRITE | FILE_BIN | FILE_SHARE_READ);
   if(h == INVALID_HANDLE)
     {
      Print("BBSQ: log write failed, error ", GetLastError());
      return;
     }
   FileSeek(h, 0, SEEK_END);
   WriteLine(h, row);
   FileClose(h);
  }
//+------------------------------------------------------------------+
````

## `tools/bbsq_reference.py`

````python
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
````

## `tools/compare_logs.py`

````python
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
````

## `tests/test_reference.py`

````python
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
````

