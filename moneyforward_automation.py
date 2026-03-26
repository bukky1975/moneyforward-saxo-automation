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
USER_DATA_DIR = os.path.join(os.path.dirname(__file__), ".playwright_data")

def scrape_moneyforward():
    if not os.path.exists(USER_DATA_DIR):
        os.makedirs(USER_DATA_DIR)

    with sync_playwright() as p:
        # 永続的なブラウザコンテキストを使用
        context = p.chromium.launch_persistent_context(
            USER_DATA_DIR,
            headless=True
        )
        page = context.new_page()

        print("マネーフォワードに接続中...", flush=True)
        page.goto("https://ssnb.x.moneyforward.com/")
        
        # すでにログインしているかチェック
        if "sign_in" not in page.url:
            print("すでにログイン済みです。", flush=True)
        else:
            print("ログインが必要です。認証を開始します...", flush=True)
            page.goto("https://ssnb.x.moneyforward.com/users/sign_in")
            
            # ページの種類を判定してログイン
            if page.locator('#sign_in_session_service_email').is_visible():
                # SSNB 独自のログインページ
                print("SSNB ログインページを検出しました。", flush=True)
                page.fill('#sign_in_session_service_email', EMAIL)
                page.fill('#sign_in_session_service_password', PASSWORD)
                page.click('#login-btn-sumit')
            else:
                # マネーフォワード ID ログインページ (リダイレクトされた場合)
                print("マネーフォワード ID ログインページを検出しました。", flush=True)
                page.fill('input[name="mfid_user[email]"]', EMAIL)
                page.click('#submitto')
                page.wait_for_selector('input[name="mfid_user[password]"]', timeout=30000)
                page.fill('input[name="mfid_user[password]"]', PASSWORD)
                page.click('#submitto')
            
            # ログイン成功待ち（ダッシュボードまたはスマート認証待ち）
            try:
                page.wait_for_url("https://ssnb.x.moneyforward.com/", timeout=120000)
                print("ログイン完了。", flush=True)
            except Exception as e:
                page.screenshot(path="error_screenshot_screenshot.png")
                print(f"ログイン待ちでタイムアウトしました。2段階認証が必要な可能性があります。スクリーンショットを保存しました: {e}", flush=True)
                raise e

        # 0. サクソバンク証券の手動口座更新
        print("Saxo資産総額の自動同期を開始...", flush=True)
        try:
            import re
            saxo_file = os.path.join(os.path.dirname(__file__), "saxo_assets.txt")
            saxo_total = None
            if os.path.exists(saxo_file):
                with open(saxo_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    match = re.search(r"ポートフォリオ(?:総資産額|総計):\s*([\d,]+(?:\.\d+)?)\s*JPY", content)
                    if match:
                        saxo_total = int(float(match.group(1).replace(",", "")))
            
            if saxo_total is not None:
                page.goto("https://ssnb.x.moneyforward.com/accounts")
                page.locator("text=サクソバンク証券").first.click()
                page.wait_for_load_state("networkidle")
                row = page.locator("tr", has_text="オプション等資産")
                if row.count() > 0:
                    row.locator('img[alt="変更"]').first.click()
                    page.wait_for_selector('input[name="user_asset_det[value]"]:visible', timeout=10000)
                    page.locator('input[name="user_asset_det[value]"]:visible').fill(str(saxo_total))
                    page.locator('input[value="この内容で登録する"]:visible').click()
                    page.wait_for_load_state("networkidle")
                    print(f"サクソバンク証券の残高を {saxo_total} 円に同期しました！", flush=True)
                else:
                    print("⚠️ サクソバンク証券のオプション等資産行が見つかりませんでした。", flush=True)
            else:
                print("⚠️ saxo_assets.txt から総資産額を読み込めませんでした。", flush=True)
        except Exception as e:
            print(f"⚠️ サクソバンク証券の同期中にエラーが発生しました: {e}", flush=True)

        # 1. 各金融機関の更新
        print("金融機関の更新を開始...", flush=True)
        page.goto("https://ssnb.x.moneyforward.com/accounts")
        # クラス名 ga-refresh-account-button を優先
        update_buttons = page.query_selector_all('.ga-refresh-account-button')
        if not update_buttons:
             update_buttons = page.query_selector_all('a:has-text("更新")')
        
        clicked_count = 0
        for btn in update_buttons:
            try:
                # ボタンが表示されており、非活性でない場合のみクリック
                if btn.is_visible() and btn.is_enabled():
                    btn.click()
                    clicked_count += 1
            except:
                pass
        print(f"{clicked_count}件の口座の更新をリクエストしました。", flush=True)
        
        # 更新完了を待機 (最大5分)
        print("更新の完了を待機中...", flush=True)
        start_wait = time.time()
        while time.time() - start_wait < 300:
            page.reload()
            updating = page.locator('tr:has-text("更新中")').count()
            if updating == 0:
                print("すべての更新が完了しました。", flush=True)
                break
            print(f"現在 {updating} 件の口座を更新中... (経過: {int(time.time() - start_wait)}秒)", flush=True)
            time.sleep(15)

        # 2. 資産詳細（ポートフォリオ）の抽出
        print("資産データの抽出を開始...", flush=True)
        page.goto("https://ssnb.x.moneyforward.com/bs/portfolio")
        page.wait_for_load_state("networkidle")
        
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
            const totalElement = document.querySelector('.bs-total-assets, .total-assets');
            results['資産総額'] = totalElement ? totalElement.innerText.trim() : '不明';
            
            return results;
        }""")

        # テキストファイルの作成
        timestamp = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        with open(LOCAL_PATH, "w", encoding="utf-8") as f:
            f.write(f"資産状況報告 ({timestamp})\n\n")
            # 抽出したデータを整形して書き込み
            for section, tables in data.items():
                if section == '資産総額':
                    continue
                
                f.write(f"--------------------------------------------------\n")
                f.write(f" {section}\n")
                f.write(f"--------------------------------------------------\n")
                for table in tables:
                    for row in table:
                        f.write(" | ".join(row) + "\n")
                    f.write("\n")
            
            # 資産総額を最後に
            f.write(f"■ 資産総額: {data.get('資産総額', '不明')}\n")

        print(f"データを {LOCAL_PATH} に保存しました。", flush=True)
        context.close()

def copy_to_drive():
    if os.path.exists(DRIVE_PATH):
        target = os.path.join(DRIVE_PATH, OUTPUT_FILENAME)
        shutil.copy2(LOCAL_PATH, target)
        print(f"Googleドライブ ({target}) にコピーしました。", flush=True)
    else:
        print(f"エラー: Googleドライブのパスが見つかりません: {DRIVE_PATH}", flush=True)

if __name__ == "__main__":
    try:
        scrape_moneyforward()
        copy_to_drive()
        print("すべての処理が完了しました。", flush=True)
    except Exception as e:
        print(f"エラーが発生しました: {e}", flush=True)
