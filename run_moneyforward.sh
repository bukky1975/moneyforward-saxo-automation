#!/bin/zsh

# スクリプトのディレクトリに移動
cd "$(dirname "$0")"

# ログ出力用（デバッグ用）
LOG_FILE="./automation.log"
echo "$(date): 実行開始" >> "$LOG_FILE"

# Pythonスクリプトの実行
# Playwrightなどのライブラリがインストールされている環境のPythonパスを指定
"./.venv/bin/python3" "./moneyforward_automation.py" >> "$LOG_FILE" 2>&1

echo "$(date): 実行完了" >> "$LOG_FILE"
