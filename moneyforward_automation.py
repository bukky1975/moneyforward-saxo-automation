import os
import time
import json
import shutil
from datetime import datetime
from playwright.sync_api import sync_playwright

from dotenv import load_dotenv

# .env を読み込み
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# --- 設定項目 ---
# 環境変数 (.env) から読み込みます
EMAIL = os.environ.get("MF_EMAIL", "")
PASSWORD = os.environ.get("MF_PASSWORD", "")

# Googleドライブの保存先パス
DRIVE_PATH = "/Users/takeko-macmini/Library/CloudStorage/GoogleDrive-bukky1975@gmail.com/マイドライブ/毎日更新"
OUTPUT_FILENAME = "assets_data.txt"
LOCAL_PATH = os.path.join(os.path.dirname(__file__), OUTPUT_FILENAME)

def scrape_moneyforward():
    with sync_playwright() as p:
        # ブラウザの起動
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        print("マネーフォワードにログイン中...")
        page.goto("https://ssnb.x.moneyforward.com/users/sign_in")
        
        # ログイン情報の入力
        page.fill('input[id="sign_in_session_service_email"]', EMAIL)
        page.fill('input[id="sign_in_session_service_password"]', PASSWORD)
        page.click('input[id="login-btn-sumit"]')
        
        # ログイン成功待ち（ダッシュボードまたはスマート認証待ち）
        page.wait_for_url("https://ssnb.x.moneyforward.com/", timeout=60000)
        print("ログイン成功。")

        # 0. サクソバンク証券の手動口座更新
        print("Saxo資産総額の自動同期を開始...")
        try:
            import re
            saxo_file = os.path.join(os.path.dirname(__file__), "saxo_assets.txt")
            saxo_total = None
            if os.path.exists(saxo_file):
                with open(saxo_file, "r", encoding="utf-8") as f:
                    match = re.search(r"ポートフォリオ(?:総資産額|総計):\s*([\d,]+(?:\.\d+)?)\s*JPY", f.read())
                    if match:
                        saxo_total = int(float(match.group(1).replace(",", "")))
            
            if saxo_total is not None:
                page.goto("https://ssnb.x.moneyforward.com/accounts")
                page.locator("text=サクソバンク証券").first.click()
                page.wait_for_load_state("networkidle")
                row = page.locator("tr", has_text="オプション等資産")
                row.locator('img[alt="変更"]').first.click()
                page.wait_for_selector('input[name="user_asset_det[value]"]:visible', timeout=10000)
                page.locator('input[name="user_asset_det[value]"]:visible').fill(str(saxo_total))
                page.locator('input[value="この内容で登録する"]:visible').click()
                page.wait_for_load_state("networkidle")
                print(f"サクソバンク証券の残高を {saxo_total} 円に同期しました！")
            else:
                print("⚠️ saxo_assets.txt から総資産額を読み込めませんでした。")
        except Exception as e:
            print(f"⚠️ サクソバンク証券の同期中にエラーが発生しました: {e}")

        # 1. 各金融機関の更新
        print("金融機関の更新を開始...")
        page.goto("https://ssnb.x.moneyforward.com/accounts")
        update_buttons = page.query_selector_all('a:has-text("更新")')
        for btn in update_buttons:
            try:
                btn.click()
            except:
                pass
        print(f"{len(update_buttons)}件の口座の更新をリクエストしました。")
        time.sleep(5)  # 更新開始を待つ

        # 2. 資産詳細（ポートフォリオ）の抽出
        print("資産データの抽出を開始...")
        page.goto("https://ssnb.x.moneyforward.com/bs/portfolio")
        
        # JavaScriptを使用して全テーブルデータを抽出
        data = page.evaluate("""() => {
            const results = {};
            const sections = Array.from(document.querySelectorAll('section, .bs-portfolio-section'));
            
            sections.forEach(section => {
                const header = section.querySelector('h1, h2, h3');
                if (!header) return;
                const sectionName = header.innerText.trim();
                
                const tables = Array.from(section.querySelectorAll('table'));
                results[sectionName] = tables.map(table => {
                    const rows = Array.from(table.querySelectorAll('tr'));
                    return rows.map(row => Array.from(row.querySelectorAll('td, th')).map(cell => cell.innerText.trim()));
                });
            });
            
            // 総資産
            const totalElement = document.querySelector('.total-assets');
            results['資産総額'] = totalElement ? totalElement.innerText.trim() : '不明';
            
            return results;
        }""")

        # テキストファイルの作成
        timestamp = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        with open(LOCAL_PATH, "w", encoding="utf-8") as f:
            f.write(f"資産状況報告 ({timestamp})\n\n")
            # 抽出したデータを整形して書き込み（簡易版）
            for section, tables in data.items():
                if section == '資産総額':
                    f.write(f"■ {section}: {tables}\n\n")
                    continue
                
                f.write(f"--------------------------------------------------\n")
                f.write(f" {section}\n")
                f.write(f"--------------------------------------------------\n")
                for table in tables:
                    for row in table:
                        f.write(" | ".join(row) + "\n")
                    f.write("\n")

        print(f"データを {LOCAL_PATH} に保存しました。")
        browser.close()

def copy_to_drive():
    if os.path.exists(DRIVE_PATH):
        target = os.path.join(DRIVE_PATH, OUTPUT_FILENAME)
        shutil.copy2(LOCAL_PATH, target)
        print(f"Googleドライブ ({target}) にコピーしました。")
    else:
        print(f"エラー: Googleドライブのパスが見つかりません: {DRIVE_PATH}")

if __name__ == "__main__":
    try:
        scrape_moneyforward()
        copy_to_drive()
        print("すべての処理が完了しました。")
    except Exception as e:
        print(f"エラーが発生しました: {e}")
