import os
import time
import pyotp
from playwright.sync_api import sync_playwright

# --- 設定項目 (環境変数からの読み込みを推奨) ---
USER_ID = os.environ.get("SAXO_USER_ID", "YOUR_USER_ID")
PASSWORD = os.environ.get("SAXO_PASSWORD", "YOUR_PASSWORD")
TOTP_SECRET = os.environ.get("SAXO_TOTP_SECRET", "YOUR_TOTP_SECRET")

def generate_totp(secret):
    if not secret or secret == "YOUR_TOTP_SECRET":
        return None
    totp = pyotp.TOTP(secret.replace(" ", ""))
    return totp.now()

def automate_saxo():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False) # 動作確認のため一旦有頭ブラウザ
        context = browser.new_context()
        page = context.new_page()

        print("SaxoTraderにログイン中...")
        page.goto("https://www.saxotrader.com/login/ja")

        # 1. ユーザーIDの入力
        # セレクタは調査結果に基づき、クラス名の一部を使用
        page.fill('input[class*="input-base"]', USER_ID)
        page.click('button:has-text("続行")')
        
        # 2. パスワードの入力 (画面遷移待ち)
        page.wait_for_selector('input[type="password"]')
        page.fill('input[type="password"]', PASSWORD)
        page.click('button:has-text("続行")')

        # 3. 2段階認証 (TOTP)
        otp_code = generate_totp(TOTP_SECRET)
        if otp_code:
            print(f"2段階認証コードを生成しました: {otp_code}")
            # 指定された入力欄を待機（セレクタは調整が必要な可能性あり）
            page.wait_for_selector('input[class*="input-base"]')
            page.fill('input[class*="input-base"]', otp_code)
            page.click('button:has-text("続行")')
        else:
            print("TOTP_SECRETが設定されていないため、2段階認証は手動入力を待機します。")
            # ログイン完了後のURL（例: ダッシュボード）への遷移を待つ
            time.sleep(30) 

        # ログイン成功待ち
        print("ログイン完了。ダッシュボードへ遷移中...")
        # URLが変わるのを待つ
        page.wait_for_load_state("networkidle")

        # 4. レポートの抽出 (ターゲットが決定次第実装)
        print("現在はログイン確認までを実装しています。")
        # 例: 資産管理 > 各種レポート へのナビゲーション
        # page.goto("https://www.saxotrader.com/...)

        print("処理を終了します。")
        time.sleep(5)
        browser.close()

if __name__ == "__main__":
    automate_saxo()
