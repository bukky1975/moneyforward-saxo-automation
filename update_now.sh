#!/bin/zsh

cd "/Users/takeko-macmini/MFSAXO"
source .venv/bin/activate

echo "======================================"
echo " Saxo Bankのデータ取得を開始します"
echo "======================================"
echo "※Saxoの認証画面が開いた場合、パスワードマネージャー等を利用して手動ログイン（承認）を行ってください。"
python saxotrader_automation.py --manual
echo ""

echo "======================================"
echo " マネーフォワードの自動更新を開始します"
echo "======================================"
python moneyforward_automation.py
echo ""

echo "======================================"
echo " 経済ニュースの自動取得を開始します"
echo "======================================"
python fetch_economic_news.py
echo ""

echo "======================================"
echo "      すべての手動更新が完了しました      "
echo "======================================"
