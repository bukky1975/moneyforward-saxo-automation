import os
import time
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

def main():
    print("ニュースフィードを取得中です...")
    news_text = fetch_rss_news()
    
    # 標準出力にも軽くプレビューを出す（多すぎるので冒頭のみ）
    preview = "\n".join(news_text.split("\n")[:15])
    print("\n[取得したニュースのプレビュー（一部）]")
    print(preview)
    print("...\n")
    
    upload_to_google_docs(news_text)

if __name__ == "__main__":
    main()
