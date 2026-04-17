import os
import time
import json
import requests
from datetime import datetime
import feedparser
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from oauth2client.service_account import ServiceAccountCredentials

GOOGLE_CREDS_FILE = os.path.join(os.path.dirname(__file__), "google_credentials.json")
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "latest_economic_news.txt")
DOC_TITLE = "最新経済ニュース（自動更新用）"

FEEDS = [
    {
        "category": "【国内ニュース】 Yahoo!ニュース（経済）",
        "url": "https://news.yahoo.co.jp/rss/categories/business.xml"
    },
    {
        "category": "【国内ニュース】 NHKニュース（ビジネス）",
        "url": "https://www.nhk.or.jp/rss/news/cat5.xml"
    },
    {
        "category": "【海外ニュース】 MarketWatch (Top Stories)",
        "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories"
    },
    {
        "category": "【海外ニュース】 Investing.com (Markets)",
        "url": "https://www.investing.com/rss/news_25.rss"
    },
    {
        "category": "【海外ニュース】 Yahoo Finance US",
        "url": "https://finance.yahoo.com/news/rssindex"
    },
    {
        "category": "【米国オプション】 Benzinga (Options)",
        "url": "https://www.benzinga.com/markets/options/feed/"
    }
]

def fetch_rss_news():
    lines = []
    lines.append("=== 最新経済ニュース ===")
    lines.append(f"取得日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # CNN Fear & Greed Indexの取得
    lines.append("■ CNN Fear & Greed Index")
    lines.append("-" * 40)
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://edition.cnn.com/'
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        fgi = data.get("fear_and_greed", {})
        score = fgi.get("score")
        rating = fgi.get("rating")
        if score is not None and rating:
            lines.append(f"・現在: {score:.2f} ({rating})")
            lines.append(f"・前日終値: {fgi.get('previous_close', 0):.2f}")
            lines.append(f"・1週間前: {fgi.get('previous_1_week', 0):.2f}")
            lines.append(f"・1ヶ月前: {fgi.get('previous_1_month', 0):.2f}")
            lines.append(f"・1年前: {fgi.get('previous_1_year', 0):.2f}")
        else:
            lines.append("  データを取得できませんでした。")
    except Exception as e:
        lines.append(f"  取得中にエラーが発生しました: {e}")
    lines.append("\n")

    # 主要市場データの取得
    lines.append("■ 主要市場データ (商品・為替・株価インデックス)")
    lines.append("-" * 40)
    market_symbols = {
        "日経平均": "^N225",
        "S&P 500": "^GSPC",
        "米ドル/円": "JPY=X",
        "ユーロ/ドル": "EURUSD=X",
        "WTI原油": "CL=F",
        "金 (Gold)": "GC=F"
    }
    import subprocess
    try:
        for name, symbol in market_symbols.items():
            url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
            try:
                # HTTP 429回避のためcurlを使用
                out = subprocess.check_output(['curl', '-s', '-A', 'Mozilla/5.0', url], timeout=10)
                data = json.loads(out)
                meta = data['chart']['result'][0]['meta']
                price = meta.get('regularMarketPrice')
                prev_close = meta.get('chartPreviousClose')
                
                if price is not None and prev_close is not None:
                    diff = price - prev_close
                    diff_pct = (diff / prev_close) * 100
                    
                    if symbol in ["^N225", "JPY=X"]:
                        lines.append(f"・{name}: {price:,.2f} 円 (前日比: {diff:+,.2f} / {diff_pct:+.2f}%)")
                    else:
                        lines.append(f"・{name}: {price:,.2f} USD (前日比: {diff:+,.2f} / {diff_pct:+.2f}%)")
                else:
                    lines.append(f"・{name}: 価格データなし")
            except Exception as e:
                lines.append(f"・{name}: 取得失敗")
    except Exception as e:
        lines.append(f"  市場データの取得中にエラーが発生しました: {e}")
    lines.append("\n")

    for feed_info in FEEDS:
        lines.append(f"■ {feed_info['category']}")
        lines.append("-" * 40)
        try:
            feed = feedparser.parse(feed_info["url"])
            if not feed.entries:
                lines.append("  ニュースを取得できませんでした。\n")
                continue
            
            # 最新の15件を取得
            for i, entry in enumerate(feed.entries[:15]):
                title = entry.get('title', 'No Title')
                published = entry.get('published', '')
                link = entry.get('link', '')
                
                lines.append(f"・{title}")
                if published:
                    lines.append(f"  {published}")
                lines.append(f"  {link}")
                lines.append("")
        except Exception as e:
            lines.append(f"  フィードの取得中にエラーが発生しました: {e}\n")
            
        lines.append("\n")

    return "\n".join(lines)

def upload_to_google_docs(text_content):
    print("\nGoogle Docsへニュースを上書き更新しています...")
    if not os.path.exists(GOOGLE_CREDS_FILE):
        print(f"アップロードスキップ: Google APIキー({GOOGLE_CREDS_FILE})が見つかりません。")
        return

    # 一時ファイルに保存
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(text_content)

    try:
        scope = ["https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDS_FILE, scope)
        service = build('drive', 'v3', credentials=creds)
        
        # ユーザー作成のファイルIDを直接指定
        file_id = "10mUskt6vWgUcb461O3CkVDH-1x4851lFui0rQg6doGA"
        
        media = MediaFileUpload(OUTPUT_FILE, mimetype='text/plain', resumable=True)
        file = service.files().update(fileId=file_id, media_body=media, fields='id').execute()
        print(f"================================================================")
        print(f"完了: Google Docs (指定ID: {file.get('id')}) に最新ニュースを上書き更新しました。")
        print(f"================================================================")
            
    except Exception as e:
        print(f"Google Docsへのアップロードに失敗しました: {e}")

def update_market_data_doc(text_content):
    print("\n市場データ集(Google Docs)のニュースを上書き更新しています...")
    if not os.path.exists(GOOGLE_CREDS_FILE):
        return

    try:
        # ドキュメントAPIにもアクセス可能なスコープ
        scope = ["https://www.googleapis.com/auth/documents", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDS_FILE, scope)
        service = build('docs', 'v1', credentials=creds)
        
        # 市場データ集のドキュメントID
        document_id = "1FNcepAUX2c_hDh5eDrMCr5qittrzVWT4qxh9_1dD-Kg"
        
        # ドキュメントの現在の末尾インデックスを取得して既存コンテンツを削除
        document = service.documents().get(documentId=document_id).execute()
        content = document.get('body').get('content')
        end_index = content[-1]['endIndex'] - 1 if content else 1
        
        requests = []
        if end_index > 1:
            requests.append({
                'deleteContentRange': {
                    'range': {
                        'startIndex': 1,
                        'endIndex': end_index
                    }
                }
            })
            
        requests.append({
            'insertText': {
                'location': {
                    'index': 1,
                },
                'text': text_content + "\n"
            }
        })
        
        service.documents().batchUpdate(documentId=document_id, body={'requests': requests}).execute()
        
        print(f"================================================================")
        print(f"完了: 市場データ集 (指定ID: {document_id}) を最新ニュースで上書きしました。")
        print(f"================================================================")
            
    except Exception as e:
        print(f"市場データ集の上書きに失敗しました: {e}")

def main():
    print("ニュースフィードを取得中です...")
    news_text = fetch_rss_news()
    
    # 標準出力にも軽くプレビューを出す（多すぎるので冒頭のみ）
    preview = "\n".join(news_text.split("\n")[:15])
    print("\n[取得したニュースのプレビュー（一部）]")
    print(preview)
    print("...\n")
    
    upload_to_google_docs(news_text)
    update_market_data_doc(news_text)

if __name__ == "__main__":
    main()
