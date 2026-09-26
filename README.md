# BB スクイーズ・アラートインジケータ

GBPJPY M15 で、BB がスクイーズからエクスパンションに切り替わった足が 2σ を終値で抜けたときに通知する裁量補助インジケータ。
cTrader 版と MT5 版を同じ仕様から独立に実装している。判定ロジックの正は [仕様書 v0.1](docs/bb_alert_indicator_spec_v0_1.md)。

| パス | 内容 |
| --- | --- |
| `ctrader/BBSqueezeAlert.cs` | cTrader Automate C# Indicator（チャート内テキスト + 音） |
| `mt5/BBSqueezeAlert.mq5` | MQL5 カスタムインジケータ（SendNotification） |
| `tools/bbsq_reference.py` | Python リファレンス実装。OHLC CSV から同形式のログ CSV を出す |
| `tools/compare_logs.py` | 2 つのログ CSV の突き合わせ（仕様 8 章の手順 2〜4） |
| `tests/test_reference.py` | リファレンス実装と突き合わせツールのテスト |

## 導入

**cTrader**: Automate → Indicators → New で `BBSqueezeAlert.cs` の中身を貼り付けてビルド。ログ書き込みのため `AccessRights.FullAccess` を要求する。出力先は `Documents\cAlgo\Data\`。

**MT5**: `BBSqueezeAlert.mq5` を `MQL5\Indicators\` に置いて MetaEditor でコンパイル。プッシュ通知は ツール → オプション → 通知 で MetaQuotes ID を登録して有効化しておく（無効のままだとエキスパートログに警告を 1 回出す）。出力先は `MQL5\Files\`。

出力ファイル名:
- ログ: `Log_FileName`。空（既定）なら `bb_alert_log_<SYMBOL>_<TF>.csv`（例: `bb_alert_log_GBPJPY_M15.csv`）なので、複数チャートに入れても衝突しない
- OHLC ダンプ（`Dump_Bars=true` のとき）: `bars_<SYMBOL>_<TF>.csv`

ビルド確認状況:
- C#: .NET 8 SDK + NuGet `cTrader.Automate` 1.0.21（target net6.0）でビルドし、警告 0・エラー 0 を確認。cTrader Automate 本体でのビルドは未確認
- MQL5: MetaEditor が入手できない環境（ダウンロードがネットワークポリシーで遮断）のためコンパイル未確認

## 実装検証（リファレンスとの完全一致）

ブローカー価格差と実装差を切り分けるため、8 章の一致確認の前に、各実装がリファレンス実装と同じ OHLC で完全一致することを確かめる。

1. `Dump_Bars=true` でインジケータを適用する（初回ロード完了時に確定足の OHLC とログが同じ足の範囲で出る）
2. ダンプした OHLC をリファレンス実装に通す
3. `--strict` で比較する。全列一致なら `EXACT MATCH`（終了コード 0）、不一致は実装のバグ

```sh
python3 tools/bbsq_reference.py bars_GBPJPY_M15.csv -o reference.csv --platform MT5
python3 tools/compare_logs.py bb_alert_log_GBPJPY_M15.csv reference.csv --strict -o strict.csv
```

- 両方とも同じ時刻基準で出るので `--ctrader-tz` / `--mt5-tz` は指定しない
- 比較はダンプ直後に行う（ダンプは初回ロード時の 1 回だけなので、その後に確定した足のシグナルはログにだけ載る）
- `strict.csv` の `diff_cols` に不一致の列名が出る。列名の `ct_` は 1 つ目の引数、`mt5_` は 2 つ目の引数

## 一致確認（cTrader と MT5）

```sh
# 両方のログを同じ日付範囲で比較（MT5 のサーバー時刻が GMT+2/+3 夏時間なら Europe/Athens）
python3 tools/compare_logs.py ctrader.csv mt5.csv \
    --ctrader-tz UTC --mt5-tz Europe/Athens --from 2026-06-26 --to 2026-09-26 -o compare.csv

# どちらかのログが仕様どおりか疑わしいとき、同じ OHLC をリファレンス実装に通す
python3 tools/bbsq_reference.py bars.csv -o reference.csv --platform MT5
```

`bars.csv` は `time,open,high,low,close`（古い順、確定足のみ。`Dump_Bars` の出力と同じ形式）。

テスト: `python3 -m unittest discover -s tests`

## 仕様の解釈（実装で決めたこと）

仕様書に書かれていない、または読み方が複数ある箇所は 3 実装とも次のとおりにそろえている。仕様書に取り込むか判断してほしい。

1. **判定開始足**: 8 章「Sq_BwLookback + BB_Period 本以降のみ判定」を、足インデックス（0 始まり）≥ `max(BB_Period + Sq_BwLookback, KC_Period, KC_AtrPeriod)` と解釈。それより前は Sq=false、SqLen=0。発火は足 i-1 が判定開始足以降のときだけ。
2. **最初の TR**: 足 0 は前の終値がないので TR_0 = High_0 − Low_0。ATR の初期値は足 0〜p−1 の TR 平均を足 p−1 に置く。EMA も足 q−1 に最初の q 本の SMA を置く。
3. **SqLen の値**: ログとメッセージの `sqlen` は解除直前の足の SqLen（仕様どおり）。`sq_mode_hit` は Sq_Mode に関係なく、解除直前の足で実際に成立していた条件を出す。
4. **スクイーズ帯の描画（未決事項）**: 暫定で下バンドの 0.5×ATR 下に点列。SqLen < Sq_MinBars は薄い色、SqLen ≥ Sq_MinBars に達した足から濃い色（遡って塗り直さない）。
5. **表示用パラメータ**: 両実装に `Show_Keltner`（既定 false）、cTrader に `Sound_File` を追加。判定には関与しない。
6. **時刻**: cTrader には「サーバー時刻」がないため UTC で出力（`TimeZone = TimeZones.UTC`）。MT5 はサーバー時刻。突き合わせ時に `compare_logs.py` で UTC にそろえる。
7. **価格の桁数**: 仕様どおり小数 3 桁固定（GBPJPY 前提）。他通貨ペアで使うなら要変更。
8. **ログの改行**: 両実装とも UTF-8（BOM なし）、CRLF。
9. **過去足の追加読込（cTrader）**: `Calculate` が評価済みより古い index（最終足以外）で呼ばれたら全足を再計算する。`BBSQ_` で始まるチャートオブジェクトを消し、ログを作り直し、再計算が最終足に届くまで通知しない。MT5 は `prev_calculated == 0` で同じ動きになる。

## 仕様書への指摘

- **BW 分位の同値**: 「BW_i 以下の本数」で数えるため、値動きがほぼ止まって BW が同値の足が並ぶと分位が高く出る（スクイーズと判定されにくい）。実データではまず起きないが、仕様の意図どおりか確認したい。
- **EMA / ATR の起点依存**: 再帰計算なので、チャートの読み込み開始位置が違うと直後の値がずれる（数十本で収束）。8 章の「両者とも同じ日付から開始」は、比較期間の開始を両方の履歴の先頭から十分後ろ（数百本以上）に置くことで満たす。
- **再接続時の通知**: 回線断などで複数の足をまとめて評価したときは、確定した足ごとに通知が出る（同じ足の重複は出ない）。
