import os
import sys
import json
import shutil
import urllib.parse
import webbrowser
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from http.server import BaseHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv
from datetime import datetime
import argparse
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
# Load .env
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

APP_KEY = os.environ.get("SAXO_APP_KEY")
APP_SECRET = os.environ.get("SAXO_APP_SECRET")
REDIRECT_URI = os.environ.get("SAXO_REDIRECT_URI", "http://localhost:12321/redirect")

TOKEN_FILE = os.path.join(os.path.dirname(__file__), "saxo_tokens.json")
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "saxo_assets.txt")
GOOGLE_CREDS_FILE = os.path.join(os.path.dirname(__file__), "google_credentials.json")
DRIVE_PATH = "/Users/takeko-macmini/Library/CloudStorage/GoogleDrive-bukky1975@gmail.com/マイドライブ/毎日更新"
SPREADSHEET_ID = "1YmXHlf-f-RHKIpX42ih0MZaghF3DpwdIo5JhS5l9fV8"

AUTH_URL = "https://live.logonvalidation.net/authorize"
TOKEN_URL = "https://live.logonvalidation.net/token"
OPENAPI_BASE_URL = "https://gateway.saxobank.com/openapi"

auth_code = None

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass # Suppress logging
    
    def do_GET(self):
        global auth_code
        parsed_path = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed_path.query)
        
        if "code" in query:
            auth_code = query["code"][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            html = "<html><body><h1>認証成功！</h1><p>このウィンドウを閉じてターミナルに戻ってください。スクリプトがデータの取得を継続します。</p></body></html>"
            self.wfile.write(html.encode('utf-8'))
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Authorization failed.")

def get_auth_code(is_manual=False):
    url = f"{AUTH_URL}?response_type=code&client_id={APP_KEY}&redirect_uri={urllib.parse.quote(REDIRECT_URI)}&state=123"
    
    global auth_code
    auth_code = None

    print(f"\n手動認証UIを起動します...\nURL: {url}", flush=True)
    
    port = int(urllib.parse.urlparse(REDIRECT_URI).port or 12321)
    
    class ReusableTCPServer(HTTPServer):
        allow_reuse_address = True
        timeout = 2.0 # 2秒ごとにタイムアウトしてループで再開（ブロッキング防止）
        
    server = ReusableTCPServer(('localhost', port), OAuthCallbackHandler)
    
    try:
        import subprocess
        # macOS環境で明示的にGoogle Chromeを指定して開く
        subprocess.run(["open", "-a", "Google Chrome", url], check=True)
    except Exception as e:
        print(f"Chrome指定での起動に失敗しました。デフォルトブラウザで開きます: {e}", flush=True)
        try:
            webbrowser.open(url)
        except Exception as ex:
            print(f"ブラウザ起動エラー: {ex}", flush=True)
            
    print("手動での認証完了を待機しています（最大180秒）...", flush=True)
    
    import time
    # URLへの事前アクセス等（faviconなど）でサーバーが終了しないよう、ループで待機する
    start_time = time.time()
    while not auth_code and (time.time() - start_time) < 180:
        server.handle_request()
        
    server.server_close()
    
    if not auth_code:
        print("認証が完了しませんでした（タイムアウト または 中断）。", flush=True)
    return auth_code

def get_tokens(code=None, refresh_token=None):
    data = {
        "client_id": APP_KEY,
        "client_secret": APP_SECRET,
    }
    if code:
        data["grant_type"] = "authorization_code"
        data["code"] = code
        data["redirect_uri"] = REDIRECT_URI
    elif refresh_token:
        data["grant_type"] = "refresh_token"
        data["refresh_token"] = refresh_token

    response = requests.post(TOKEN_URL, data=data)
    response.raise_for_status()
    tokens = response.json()
    
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f)
    return tokens

def load_tokens():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)
    return None

def normalize_name(name):
    """すべてのスペースを削除し大文字化（比較用マッチャー）"""
    return name.replace(" ", "").upper() if name else ""

def generate_target_sheet_name(pos):
    """建玉データ（JSON）から推測される正規化用のシート名を生成"""
    display_fmt = pos.get("DisplayAndFormat", {})
    symbol = display_fmt.get("Symbol", "")
    ticker = symbol.split('/')[0] if '/' in symbol else ""
    
    opt_data = pos.get("PositionBase", {}).get("OptionsData", {})
    expiry_raw = opt_data.get("ExpiryDate", "")
    if expiry_raw:
        dt = datetime.strptime(expiry_raw.split("T")[0], "%Y-%m-%d")
        expiry_str = dt.strftime("%b%Y") # 例: Jun2027
    else:
        expiry_str = ""
        
    strike = opt_data.get("Strike", "")
    if isinstance(strike, float) and strike.is_integer():
        strike_str = str(int(strike))
    else:
        strike_str = str(strike)
        
    put_call = opt_data.get("PutCall", "")
    pc_str = put_call[0].upper() if put_call else ""
    
    # 完全に空白を抜いた形式（例: "XSPJun2027590C"）
    target = f"{ticker}{expiry_str}{strike_str}{pc_str}"
    return target

def update_google_sheets(positions):
    """Saxo建玉データをGoogleスプレッドシートの個別シートへ更新"""
    if not os.path.exists(GOOGLE_CREDS_FILE):
        print(f"\n[スプレッドシート連携スキップ] Google APIキー ({GOOGLE_CREDS_FILE}) が見つかりませんでした。書き込みを行うためにはキーJSONファイルを配置してください。")
        return
        
    print("\nGoogleスプレッドシートへデータを更新しています...")
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDS_FILE, scope)
    client = gspread.authorize(creds)
    
    try:
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"スプレッドシートへのアクセスに失敗しました: {repr(e)}")
        return
        
    try:
        spx_sheet = spreadsheet.worksheet("SPX")
        now_str = datetime.now().strftime("%Y/%m/%d %H:%M")
        spx_sheet.update_acell("A1", f"最終更新: {now_str}")
        print(f"\n- シート 'SPX' の A1 セルにタイムスタンプ({now_str})を記録しました。")
    except Exception as e:
        print(f"\n- 警告: 'SPX' シートへのタイムスタンプ記録に失敗しました: {e}")
        
    worksheets = spreadsheet.worksheets()
    # シートタイトルを正規化してDictにマップ
    sheet_map = {normalize_name(ws.title): ws for ws in worksheets}
    
    from datetime import timedelta
    # 米国の日付に合わせるため、前日の日付を取得
    today_dt = datetime.now() - timedelta(days=1)
    today_str = today_dt.strftime("%Y/%m/%d")
    
    for pos in positions:
        asset_type = pos.get("PositionBase", {}).get("AssetType", "")
        if "Option" not in asset_type:
            continue
            
        target_name = normalize_name(generate_target_sheet_name(pos))
        
        if target_name in sheet_map:
            ws = sheet_map[target_name]
            
            amount = pos.get("PositionBase", {}).get("Amount", 0)
            purchase_price = pos.get("PositionBase", {}).get("OpenPrice", 0)
            current_price = pos.get("PositionView", {}).get("CurrentPrice", 0)
            pl = pos.get("PositionView", {}).get("ProfitLossOnTrade", 0)
            
            # カスタム保存したグリークス情報
            custom = pos.get("CustomGreeks", {})
            delta = custom.get("Delta", "")
            gamma = custom.get("Gamma", "")
            vega = custom.get("Vega", "")
            theta = custom.get("Theta", "")
            iv = custom.get("IV", "")
            
            # A:日付, B:数量, C:購入価格, D:現在値, E:評価損益
            row_data_base = [today_str, amount, purchase_price, current_price, pl]
            # I:IV, J:Delta, K:Gamma, L:Vega, M:Theta
            row_data_greeks = [iv, delta, gamma, vega, theta]
            
            # 列Aの最初の空行を探す (先頭からスキャンして、空行または今日の日付の行を特定)
            col_a = ws.col_values(1)
            row_index = 4 # データは通常4行目から開始
            for i, val in enumerate(col_a):
                if i < 3: continue # 1-3行目はスキップ
                if not val.strip() or val == today_str:
                    row_index = i + 1
                    break
            else:
                row_index = len(col_a) + 1
            
            # A列からE列まで基本データを書き込み
            ws.update(range_name=f"A{row_index}:E{row_index}", values=[row_data_base])
            # F列からJ列にかけてグリークス(IV, Delta, Gamma, Vega, Theta)を書き込み
            ws.update(range_name=f"F{row_index}:J{row_index}", values=[row_data_greeks])
            
            print(f"- シート '{ws.title}' に本日のデータを記録しました！ (行: {row_index})", flush=True)
        else:
            print(f"- 警告: 対応するシートが見つからないためスキップ: (推測キー: {generate_target_sheet_name(pos)})", flush=True)

def upload_to_google_docs():
    """レポートファイル(output.txt)をすでに作成済みのDocsへ上書き保存"""
    print("\nGoogle Docsへレポートを上書き更新しています...")
    if not os.path.exists(GOOGLE_CREDS_FILE):
        print(f"アップロードスキップ: Google APIキー({GOOGLE_CREDS_FILE})が見つかりません。")
        return

    try:
        scope = ["https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDS_FILE, scope)
        service = build('drive', 'v3', credentials=creds)
        
        doc_title = "Saxo Bank 資産レポート（自動更新用）"
        # オーナーのユーザー自身がすでに作成したファイルを検索する
        query = f"name='{doc_title}' and mimeType='application/vnd.google-apps.document' and trashed=false"
        results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        files = results.get('files', [])
        
        if not files:
            print(f"エラー: Google Docs '{doc_title}' が見つかりませんでした。ご自身のドライブにて該当名で空のDocsを新規作成してください。")
            return
            
        file_id = files[0].get('id')
        media = MediaFileUpload(OUTPUT_FILE, mimetype='text/plain', resumable=True)
        # 更新(update)のみを行う（サービスアカウントは容量ゼロのためcreateできない）
        file = service.files().update(fileId=file_id, media_body=media, fields='id').execute()
        print(f"- 既存のGoogle Docs '{doc_title}' にデータを上書き更新しました。(ID: {file.get('id')})")
            
    except Exception as e:
        print(f"Google Docsへのアップロードに失敗しました: {e}")

def fetch_and_save_portfolio(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    
    client_resp = requests.get(f"{OPENAPI_BASE_URL}/port/v1/clients/me", headers=headers)
    client_resp.raise_for_status()
    client_key = client_resp.json()["ClientKey"]
    
    balance_resp = requests.get(f"{OPENAPI_BASE_URL}/port/v1/balances/?ClientKey={client_key}", headers=headers)
    balance_resp.raise_for_status()
    bal_data = balance_resp.json()
    
    pos_url = f"{OPENAPI_BASE_URL}/port/v1/positions/me/?ClientKey={client_key}&FieldGroups=PositionBase,PositionView,DisplayAndFormat,Greeks"
    pos_resp = requests.get(pos_url, headers=headers)
    pos_resp.raise_for_status()
    positions_raw = pos_resp.json().get("Data", [])
    
    # 建玉の集約（同一UICをまとめる）
    aggregated = {}
    for pos in positions_raw:
        uic = pos.get("PositionBase", {}).get("Uic")
        if not uic:
            continue
        
        if uic not in aggregated:
            aggregated[uic] = pos
        else:
            base = aggregated[uic]
            base_amt = base["PositionBase"]["Amount"]
            new_amt = pos["PositionBase"]["Amount"]
            base_price = base["PositionBase"]["OpenPrice"]
            new_price = pos["PositionBase"]["OpenPrice"]
            
            total_amt = base_amt + new_amt
            if total_amt != 0:
                # 加重平均の計算: (価格1 * 数量1 + 価格2 * 数量2) / 合計数量
                weighted_price = (base_price * base_amt + new_price * new_amt) / total_amt
                base["PositionBase"]["OpenPrice"] = weighted_price
            
            base["PositionBase"]["Amount"] = total_amt
            # 評価損益も合算
            base["PositionView"]["ProfitLossOnTrade"] = base["PositionView"].get("ProfitLossOnTrade", 0) + pos["PositionView"].get("ProfitLossOnTrade", 0)
            
    positions = list(aggregated.values())

    output_lines = [
        f"--- Saxo Bank 資産レポート ---",
        f"取得日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ""
    ]
    
    output_lines.append("[口座残高]")
    currency = bal_data.get("Currency", "JPY")
    total_value = bal_data.get("TotalValue", 0)
    cash_balance = bal_data.get("CashBalance", 0)
    output_lines.append(f"  ポートフォリオ総計: {total_value:,.2f} {currency}")
    output_lines.append(f"  現金残高: {cash_balance:,.2f} {currency}")
    
    output_lines.append("\n[保有建玉]")
    if not positions:
        output_lines.append("  現在保有している建玉はありません。")
        
    for pos in positions:
        asset_type = pos.get("PositionBase", {}).get("AssetType", "")
        amount = pos.get("PositionBase", {}).get("Amount", 0)
        open_price = pos.get("PositionBase", {}).get("OpenPrice", 0)
        current_price = pos.get("PositionView", {}).get("CurrentPrice", 0)
        profit_loss = pos.get("PositionView", {}).get("ProfitLossOnTrade", 0)
        
        display_fmt = pos.get("DisplayAndFormat", {})
        display_name = display_fmt.get("Description", "Unknown")
        symbol = display_fmt.get("Symbol", "N/A")
        
        output_lines.append(f"- {display_name} ({asset_type})")
        output_lines.append(f"  シンボル: {symbol}")
        
        if "Option" in asset_type:
            opt_data = pos.get("PositionBase", {}).get("OptionsData", {})
            expiry_raw = opt_data.get("ExpiryDate", "")
            expiry = expiry_raw.split("T")[0] if expiry_raw else "N/A"
            strike = opt_data.get("Strike", "N/A")
            put_call = opt_data.get("PutCall", "N/A")
            
            output_lines.append(f"  期日: {expiry}, 権利行使価格: {strike}, {put_call}")
            
            # グリークス取得と保存
            greeks = pos.get("Greeks", {})
            pos["CustomGreeks"] = {
                "Delta": "", "Gamma": "", "Theta": "", "Vega": "", "IV": ""
            }
            if greeks:
                delta = greeks.get("InstrumentDelta", "")
                gamma = greeks.get("InstrumentGamma", "")
                theta = greeks.get("InstrumentTheta", "")
                vega  = greeks.get("InstrumentVega", "")
                implied_vol = greeks.get("MidVol", "")
                
                pos["CustomGreeks"] = {
                    "Delta": delta, "Gamma": gamma, "Theta": theta, "Vega": vega, "IV": implied_vol
                }
                
                output_lines.append(f"  グリークス: Delta={delta}, Gamma={gamma}, Theta={theta}, Vega={vega}")
            else:
                output_lines.append(f"  グリークス: N/A (市場データ購読なし等により取得不可)")
        
        output_lines.append(f"  数量: {amount}")
        output_lines.append(f"  取得単価: {open_price}")
        output_lines.append(f"  現在価格: {current_price}")
        output_lines.append(f"  評価損益: {profit_loss:,.2f}")
    
    output_text = "\n".join(output_lines)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(output_text)
    
    print(output_text)
    print(f"\nデータを {OUTPUT_FILE} に保存しました。")
    
    # 最後にローカルに保存した建玉情報を使ってGoogle Sheetsを更新
    update_google_sheets(positions)
    
    # Google Docs形式でアップロード
    upload_to_google_docs()

def main():
    parser = argparse.ArgumentParser(description="Saxo Bank Automation Tool")
    parser.add_argument("--manual", action="store_true", help="Launch manual login UI if auto-login fails.")
    args = parser.parse_args()

    if not APP_KEY or not APP_SECRET:
        print("エラー: .env に SAXO_APP_KEY と SAXO_APP_SECRET が正しく設定されていません。", flush=True)
        sys.exit(1)

    tokens = load_tokens()
    
    try:
        if tokens and "refresh_token" in tokens:
            print("既存のトークンを使って認証を更新中...", flush=True)
            tokens = get_tokens(refresh_token=tokens["refresh_token"])
        else:
            print("初回認証が必要です...", flush=True)
            code = get_auth_code(is_manual=args.manual)
            if code:
                tokens = get_tokens(code=code)
    except Exception as e:
        print(f"トークンの更新に失敗しました。再認証を行います。 ({e})", flush=True)
        code = get_auth_code(is_manual=args.manual)
        if code:
            tokens = get_tokens(code=code)
        else:
            tokens = None # 認証が完了しなかった場合は古いトークンを破棄
            
    if tokens and "access_token" in tokens:
        print("APIからポートフォリオデータを取得中...", flush=True)
        try:
            fetch_and_save_portfolio(tokens["access_token"])
        except Exception as ex:
            print(f"ポートフォリオデータの取得中にエラーが発生しました: {ex}", flush=True)
    else:
        print("\n[中断] 有効なアクセストークンが取得できなかったため、Saxo Bankのデータ更新とスプレッドシートへの書き込みをスキップしました。", flush=True)

if __name__ == "__main__":
    main()
