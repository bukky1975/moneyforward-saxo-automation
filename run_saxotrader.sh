#!/zsh

# スクリプトのディレクトリに移動
cd "/Users/takeko-macmini/Desktop/実験室/"

# ログ出力用
LOG_FILE="/Users/takeko-macmini/Desktop/実験室/saxo_automation.log"
echo "$(date): SaxoTrader 実行開始" >> "$LOG_FILE"

# 設定情報（シークレットなど）を環境変数として読み込む例
# export SAXO_USER_ID="xxx"
# export SAXO_PASSWORD="xxx"
# export SAXO_TOTP_SECRET="xxx"

# Pythonスクリプトの実行
"/Users/takeko-macmini/Desktop/実験室/.venv/bin/python3" "/Users/takeko-macmini/Desktop/実験室/saxotrader_automation.py" >> "$LOG_FILE" 2>&1

echo "$(date): SaxoTrader 実行完了" >> "$LOG_FILE"
