# BBスクイーズ・アラートインジケータ レビュー依頼パッケージ

このファイル 1 本に、仕様書・実装コード・設計判断・既知の論点をすべてまとめています。前提知識なしでレビューできます。

- リポジトリ: kajiura-eng/Bollinger_ins（ブランチ `claude/new-session-m1za20`）
- 状態: 仕様書 v0.1（Sep 26 改訂）に基づく実装の第 2 版（過去足の追加読込、ログ名の自動生成、Dump_Bars に対応）
  - C#: .NET 8 SDK + NuGet `cTrader.Automate` 1.0.21 でビルドし、警告 0・エラー 0（cTrader 本体では未確認）
  - MQL5: MetaEditor が入手できずコンパイル未確認 → **MQL5 の API 誤用・コンパイルエラーを重点的に見てほしい**
  - Python リファレンス実装のテスト 14 件は成功

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
12. **過去足の追加読込（cTrader）**: `Calculate(index)` で `index <= _processed && index < Bars.Count - 1` なら全足再計算（`BBSQ_` 前綴のオブジェクト削除、ログ作り直し、`_live=false`）。再計算が最終足に届いたら `_live=true`。MT5 は `prev_calculated == 0` で同じ動き
13. **ログ名**: `Log_FileName` が空（既定）なら `bb_alert_log_<SYMBOL>_<TF>.csv`。ファイル名に使えない文字は `_` に置換
14. **Dump_Bars**: 初回ロード（または再計算）完了時に確定足 0..最終確定足の OHLC を `bars_<SYMBOL>_<TF>.csv` へ出力。価格はシンボルの桁数、時刻はログと同じ基準。`compare_logs.py --strict` でリファレンスとの全列一致を確認する

## 仕様書への指摘（作成者の見解）

- **BW 分位の同値**: 「BW_i 以下の本数」なので同値の BW が並ぶと分位が高く出る（スクイーズ判定されにくい）
- **EMA / ATR の起点依存**: 再帰計算のため履歴の開始位置で初期の値がずれる。比較期間は両方の履歴の先頭から十分後ろに置く必要がある
- **再接続時の通知**: 複数の足をまとめて評価したときは足ごとに通知が出る（同じ足の重複はない）
- **BB_Period が小さいと抜けない**: 母集団σでは外れ値 1 本の z は最大 (n−1)/√n。n ≤ 5 では 2σ を超えられない（既定値 20 では問題なし）

---

