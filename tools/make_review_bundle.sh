#!/bin/sh
# レビュー依頼パッケージ docs/review_bundle.md を作り直す（ヘッダ + 仕様書 + 全コード）
set -e
cd "$(dirname "$0")/.."
out=docs/review_bundle.md
section() { # $1=path $2=lang
  printf '## `%s`\n\n````%s\n' "$1" "$2"; cat "$1"; printf '````\n\n'; }
{
  cat tools/review_bundle_header.md
  section docs/bb_alert_indicator_spec_v0_1.md markdown
  section ctrader/BBSqueezeAlert.cs csharp
  section mt5/BBSqueezeAlert.mq5 cpp
  section tools/bbsq_reference.py python
  section tools/compare_logs.py python
  section tests/test_reference.py python
} > "$out"
echo "wrote $out"
