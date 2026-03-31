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
        
        print("ブラウザを起動しました。マネーフォワードのログインと2段階認証を完了させてください。")
        print("完了したら、ダッシュボードに移動し、SaxoBankの認証に進みます。")
        
        try:
            # マネフォのダッシュボードに移動するのを待つ
            page.wait_for_url("https://ssnb.x.moneyforward.com/", timeout=0)
            print("マネーフォワードの認証を検知しました。続いてSaxo Bankの認証画面を開きます...\n")
            
            # Saxo認証ページ
            saxo_url = "https://live.logonvalidation.net/authorize?response_type=code&client_id=2d1e8e99750b4c009c104b01cc7f1c0d&redirect_uri=http%3A//localhost%3A12321/redirect&state=123"
            page.goto(saxo_url)
            
            print("Saxo Bankのログイン設定・承認を行ってください。")
            print("「接続できません（localhost）」の画面が表示されるか、URLが localhost になったら完了です。")
            
            try:
                page.wait_for_url("http://localhost:12321/redirect*", timeout=0)
                print("Saxo Bankの認証成功を検知しました！")
            except Exception:
                print("Saxoの認証画面で中断されました。")
                
            print("\nすべての手動ログインのセッション保存が完了しました。ブラウザを閉じます。")
        except Exception as e:
            print(f"セッション保存中に中断されました: {e}")
        finally:
            context.close()

if __name__ == "__main__":
    manual_login()
