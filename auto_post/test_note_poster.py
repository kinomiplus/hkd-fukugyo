#!/usr/bin/env python3
"""
note_poster.py の完全テスト。
実際に記事を投稿し、成功を確認してSlack通知を送る。
"""
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def main():
    headless = "--no-headless" not in sys.argv

    logger.info("=== note_poster.py テスト開始 (headless=%s) ===", headless)

    from note_poster import NotePoster
    from notify import notify_note_posted, notify_error

    test_title = f"【テスト】北海道副業ナビ 自動投稿テスト {int(time.time())}"
    test_content = (
        "これは自動投稿システムのテスト記事です。\n\n"
        "北海道在住の会社員向けに、副業・転職情報を発信している「北海道副業ナビ」の"
        "自動投稿システムが正常に動作していることを確認するためのテストです。\n\n"
        "## テスト内容\n\n"
        "- タイトル入力（React textarea）\n"
        "- 本文入力（ProseMirror ClipboardEvent）\n"
        "- 公開フロー（公開に進む → 投稿する）\n"
        "- 公開URL確認\n\n"
        "このテストが成功すれば、自動投稿システムは100%動作しています。\n\n"
        "北海道副業ナビ @hkd_fukugyo"
    )

    poster = None
    try:
        poster = NotePoster(headless=headless)

        # ログイン
        logger.info("ログイン中...")
        if not poster.login():
            logger.error("ログイン失敗")
            notify_error("test_note_poster.py", "ログイン失敗")
            sys.exit(1)
        logger.info("ログイン成功")

        # 記事投稿
        logger.info("記事投稿中: %s", test_title)
        start = time.time()
        article_url = poster.create_article(test_title, test_content)
        elapsed = time.time() - start

        if article_url:
            logger.info("投稿成功！ (%.1f秒)", elapsed)
            logger.info("URL: %s", article_url)

            # URL形式確認
            if "note.com" in article_url and "editor.note.com" not in article_url:
                logger.info("[OK] URLはnote.comドメイン")
            else:
                logger.warning("[NG] URLがeditor.note.comのまま: %s", article_url)

            if "/n/" in article_url:
                logger.info("[OK] /n/ パターンを確認")
            else:
                logger.warning("[NG] /n/ パターンなし: %s", article_url)

            # Slack成功通知
            notify_note_posted(test_title, article_url, len(test_content))
            logger.info("Slack通知送信完了")
            logger.info("=== テスト成功 ===")
        else:
            logger.error("投稿失敗: create_article() が None を返しました")
            notify_error("test_note_poster.py", "create_article()がNoneを返しました")
            sys.exit(1)

    except Exception as e:
        logger.error("テスト中にエラー: %s", e, exc_info=True)
        try:
            from notify import notify_error
            notify_error("test_note_poster.py", str(e))
        except Exception:
            pass
        sys.exit(1)
    finally:
        if poster:
            poster.close()


if __name__ == "__main__":
    main()
