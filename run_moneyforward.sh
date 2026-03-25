#!/bin/zsh

# スクリプトのディレクトリに移動
cd "/Users/takeko-macmini/Desktop/実験室/"

# ログ出力用（デバッグ用）
LOG_FILE="/Users/takeko-macmini/Desktop/実験室/automation.log"
echo "$(date): 実行開始" >> "$LOG_FILE"

# Pythonスクリプトの実行
# Playwrightなどのライブラリがインストールされている環境のPythonパスを指定
"/Users/takeko-macmini/Desktop/実験室/.venv/bin/python3" "/Users/takeko-macmini/Desktop/実験室/moneyforward_automation.py" >> "$LOG_FILE" 2>&1

echo "$(date): 実行完了" >> "$LOG_FILE"
