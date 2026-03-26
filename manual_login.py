import os
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

# .env を読み込み
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

USER_DATA_DIR = os.path.join(os.path.dirname(__file__), ".playwright_data")

def manual_login():
    if not os.path.exists(USER_DATA_DIR):
        os.makedirs(USER_DATA_DIR)

    with sync_playwright() as p:
        # 手動ログインのために headless=False で起動
        context = p.chromium.launch_persistent_context(
            USER_DATA_DIR,
            headless=False,
            slow_mo=500
        )
        page = context.new_page()
        page.goto("https://ssnb.x.moneyforward.com/users/sign_in")
        
        print("ブラウザを起動しました。ログインと2段階認証を完了させてください。")
        print("完了したら、ブラウザを閉じるか、このスクリプトを終了（Ctrl+C）してください。")
        
        try:
            # ユーザーがログインしてダッシュボードに移動するのを待つ（またはブラウザが閉じられるまで）
            page.wait_for_url("https://ssnb.x.moneyforward.com/", timeout=0)
        except Exception as e:
            print(f"セッション保存中に中断されました: {e}")
        finally:
            context.close()

if __name__ == "__main__":
    manual_login()
