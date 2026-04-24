#!/usr/bin/env python3
"""
note.com 自動投稿スクリプト
cronから呼び出される。記事を生成してnote.comに投稿する。

使い方:
  python post_note.py             # 通常実行（headlessモード）
  python post_note.py --no-headless  # ブラウザを表示（初回ログイン確認用）
  python post_note.py --dry-run   # 投稿せず記事内容だけ確認
"""
import argparse
import datetime
import logging
import sys
from pathlib import Path

# ログ設定
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
today = datetime.date.today().strftime("%Y%m%d")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"note_{today}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="note.com 自動投稿スクリプト")
    parser.add_argument("--no-headless", action="store_true", help="ブラウザを表示する（デバッグ用）")
    parser.add_argument("--dry-run", action="store_true", help="実際には投稿せず内容だけ表示")
    args = parser.parse_args()

    headless = not args.no_headless
    logger.info("=== note自動投稿 開始 (headless=%s) ===", headless)

    # 記事生成
    try:
        from claude_generator import generate_note_article, load_history, record_note_article
        result = generate_note_article()
    except Exception as e:
        logger.error("記事生成失敗: %s", e)
        from notify import notify_error
        notify_error("post_note.py / 記事生成", str(e))
        sys.exit(1)

    title = result["title"]
    content = result["content"]
    meta_desc = result.get("meta_description", "")
    seo_keywords = result.get("seo_keywords", {})

    logger.info("タイトル: %s", title)
    logger.info("文字数: %d文字", len(content))
    if seo_keywords:
        logger.info("SEOキーワード(primary): %s", seo_keywords.get("primary", ""))
        longtail = seo_keywords.get("longtail", [])
        if longtail:
            logger.info("ロングテール: %s", " / ".join(longtail[:3]))
    if meta_desc:
        logger.info("メタディスクリプション(%d字): %s", len(meta_desc), meta_desc)
    logger.info("--- 記事プレビュー (先頭200文字) ---\n%s…", content[:200])

    if args.dry_run:
        logger.info("【DRY RUN】実際の投稿はスキップします。")
        if meta_desc:
            logger.info("--- メタディスクリプション ---\n%s", meta_desc)
        logger.info("--- 記事全文 ---\n%s", content)
        return

    # note.comに投稿
    poster = None
    try:
        from note_poster import NotePoster
        poster = NotePoster(headless=headless)

        if not poster.login():
            logger.error("ログイン失敗。.envのNOTE_EMAIL / NOTE_PASSWORDを確認してください。")
            sys.exit(1)

        article_url = poster.create_article(title, content)

    except Exception as e:
        logger.error("投稿中にエラー: %s", e)
        from notify import notify_error
        notify_error("post_note.py / note投稿", str(e))
        sys.exit(1)
    finally:
        if poster:
            poster.close()

    if article_url is None:
        logger.error("記事の投稿に失敗しました。")
        from notify import notify_error
        notify_error("post_note.py / note投稿", "article_urlがNullでした。ログを確認してください。")
        sys.exit(1)

    # 履歴に記録
    history = load_history()
    record_note_article(history, title, article_url)

    # Slack通知（投稿完了）
    from notify import notify_note_posted
    notify_note_posted(title, article_url, len(content))

    logger.info("=== 完了 | URL: %s ===", article_url)


if __name__ == "__main__":
    main()
