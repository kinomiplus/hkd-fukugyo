"""設定・コンテキスト読み込み・テーマ管理"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

# --- APIキー ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
X_API_KEY = os.getenv("X_API_KEY", "")
X_API_SECRET = os.getenv("X_API_SECRET", "")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN", "")
X_ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET", "")
NOTE_EMAIL = os.getenv("NOTE_EMAIL", "")
NOTE_PASSWORD = os.getenv("NOTE_PASSWORD", "")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")

# --- Google Sheets ---
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")
SHEET_NAME = os.getenv("SHEET_NAME", "X投稿管理")
GOOGLE_CREDENTIALS_FILE = os.getenv(
    "GOOGLE_CREDENTIALS_FILE",
    str(BASE_DIR / "google_credentials.json"),
)

# --- パス ---
COMPANY_DIR = BASE_DIR.parent
CONTEXT_DIR = COMPANY_DIR / "context"
HISTORY_FILE = BASE_DIR / "post_history.json"
COOKIES_FILE = BASE_DIR / "note_cookies.json"
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)


def load_context() -> str:
    """コンテキストファイルを読み込んでシステムプロンプトを構築する"""
    files = [
        CONTEXT_DIR / "about-me.md",
        CONTEXT_DIR / "target.md",
        CONTEXT_DIR / "strategy.md",
        COMPANY_DIR / "employee/05_post/CLAUDE.md",
    ]
    parts = []
    for f in files:
        if f.exists():
            parts.append(f"## {f.stem}\n{f.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)


CONTEXT = load_context()

# --- 投稿時間帯の説明 ---
TIME_SLOTS = {
    "07": "朝（出勤前・通勤中に読む時間帯）",
    "12": "昼（ランチタイムに読む時間帯）",
    "17": "夕方（退勤・帰宅時間帯）",
    "20": "夜（帰宅後にゆっくり読む時間帯）",
    "22": "深夜（寝る前に読む時間帯）",
}

# --- Xテーマ一覧（20テーマを循環）---
X_THEMES = [
    "北海道でできる副業ランキング",
    "転職エージェントの正しい選び方",
    "在宅ワーク求人の探し方",
    "副業初心者が最初にやるべきこと",
    "北海道の給料が低い理由と解決策",
    "スキルなしでできる副業3選",
    "転職で年収100万円上げた体験談",
    "リモートワーク転職の現実",
    "副業で月5万円稼ぐロードマップ",
    "北海道転職市場の実態2024",
    "Webライターで月3万円稼ぐ方法",
    "副業の確定申告の基礎知識",
    "転職活動を始めるべきタイミング",
    "ポイ活で月1万円稼ぐ具体的な方法",
    "クラウドワークスで最初の1万円",
    "北海道でリモートワークできる会社の探し方",
    "副業と本業を両立するコツ",
    "転職の志望動機の書き方",
    "フリーランスになる前に知っておくこと",
    "北海道在住が使うべき転職サイト比較",
]

# --- note記事テーマ一覧 ---
NOTE_THEMES = [
    "北海道在住が副業で月5万円稼いだ完全ロードマップ",
    "札幌から転職して年収100万円上げた話【実体験】",
    "北海道でできる在宅副業5選と始め方",
    "転職エージェントを使うべき人・使わない方がいい人",
    "副業初心者が最初にやるべき3つのこと",
    "北海道転職市場の現実と攻略法",
    "Webライターで月3万円稼ぐまでにやったこと全部",
    "スキルなしの北海道会社員が副業を始めた結果",
    "リモートワーク求人の探し方【北海道版完全ガイド】",
    "転職活動を3ヶ月で成功させた方法",
    "ポイ活・アンケートサイトで月1万円稼ぐ具体的な手順",
    "北海道でフリーランスになる前に知っておくべき現実",
]

# Studio LP URL
LP_URL = "https://salmon381207.studio.site"
