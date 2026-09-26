# BBスクイーズ・アラートインジケータ 共通仕様書 v0.1

Sep 26, 2026 · @TOSHIKI

改訂（Sep 26, 2026）: ATR 記述の修正、cTrader の時刻は UTC、過去足の追加読込時の再計算、Log_FileName の自動生成、Dump_Bars 追加、実装とリファレンスの完全一致確認手順

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
| Log_FileName | string | （空） | ログファイル名。空なら bb_alert_log_<SYMBOL>_<TF>.csv を自動生成（複数チャートでの衝突防止） |
| Dump_Bars | bool | false | true なら初回ロード完了時に確定足の OHLC を bars_<SYMBOL>_<TF>.csv へ出力（8 章の実装検証用） |

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

**ATR**（Wilder 方式。両実装ともこの式で自前計算する。MT5 標準の iATR は TR の単純移動平均で Wilder ではないため使わない）

```latex
TR_i = \max(High_i-Low_i,\ |High_i-Close_{i-1}|,\ |Low_i-Close_{i-1}|),\quad
ATR_i = \frac{(p-1)\,ATR_{i-1}+TR_i}{p}
```

p = KC_AtrPeriod。初期値 ATR は最初の p 本の TR 単純平均。足 0 は前の終値がないので TR_0 = High_0 − Low_0。

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
| 再計算 | チャート再読込・パラメータ変更・過去足の追加読込で、過去シグナルの描画とログは作り直し、通知は出さない | Calculate が評価済みより古い index（最終足以外）で呼ばれたら全足を再計算。"BBSQ_" 前綴のチャートオブジェクトを削除しログを作り直す | prev_calculated==0 で全足を再計算 |

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

方向は UP / DOWN、時刻は足の開始時刻（MT5 はサーバー時刻、cTrader は UTC）。sqlen は解除直前の SqLen。MT5 の SendNotification は 255 文字制限があるので、このフォーマットに収める。

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

- bar_time は足の開始時刻（YYYY-MM-DD HH:MM。MT5 はサーバー時刻、cTrader はサーバー時刻の概念がないため UTC）
- 価格は小数 3 桁、bw_pct は小数 1 桁
- sq_mode_hit は解除直前足で成立していた条件（KC / BW / BOTH）
- 保存先: cTrader は Documents\\cAlgo\\Data 配下、MT5 は MQL5\\Files 配下。ファイル名は Log_FileName（空なら bb_alert_log_<SYMBOL>_<TF>.csv）
- 初回ロード時の過去足シグナルも同じ形式で書き出す（過去分の突き合わせに使う）。重複防止のため、起動時は過去足分でファイルを作り直し（上書き）、以後の新規シグナルのみ追記する。突き合わせ用に残したい場合は起動前にファイルを退避する

## 8. プラットフォーム差異と一致確認

計算式を揃えても、データとサーバー時刻の違いで完全一致はしない。許容範囲を先に決めておく。

| 差異の源 | 影響 | 対処 |
| --- | --- | --- |
| ブローカーの価格データ（Bid ベース、フィード差） | Close が 0.1〜0.5 pips ずれ、バンド際の足で発火有無が分かれる | 許容。不一致足はログで理由（close と upper/lower の差）を記録して裁量比較の注記にする |
| 時刻の基準（cTrader は UTC、MT5 はサーバー時刻） | bar_time がずれる | 突き合わせ時に両方を UTC に補正（compare_logs.py の --ctrader-tz / --mt5-tz）。M15 の足境界は 15 分単位なので判定自体は影響なし |
| 週明け・祝日のギャップ足 | 両者で足数が違うと SqLen がずれる | 日足境界ではなく足数で計算しているので、欠損足がある側は SqLen が短くなる。発火不一致の主要因候補として記録 |
| 過去足の本数 | パーセンタイルの参照窓の起点がずれる | 初回ロード時は Sq_BwLookback + BB_Period 本以降のみ判定。両者とも同じ日付から開始 |

**実装検証（一致確認の前に行う）**

ブローカー価格差と実装差を切り分けるため、先に各実装がリファレンス実装（tools/bbsq_reference.py）と同じ OHLC で完全一致することを確かめる。

1. Dump_Bars=true で各実装をチャートに適用し、bars_<SYMBOL>_<TF>.csv とログ CSV を得る
2. bars CSV をリファレンス実装に通してログを作る
3. compare_logs.py --strict で実装ログとリファレンスのログを比較し、全列の完全一致を確認する（不一致は実装のバグ）

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
