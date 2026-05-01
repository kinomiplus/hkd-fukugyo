#!/usr/bin/env python3
"""
X (Twitter) 自動投稿スクリプト
cronから呼び出される。実行時刻に合わせたポストを生成して投稿する。

使い方:
  python post_x.py           # 現在時刻を自動判定
  python post_x.py --hour 07 # 時刻を手動指定（テスト用）
  python post_x.py --dry-run # 投稿せず内容だけ確認
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
        logging.FileHandler(LOG_DIR / f"x_{today}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="X 自動投稿スクリプト")
    parser.add_argument("--hour", help="投稿時間帯 (例: 07, 12, 17, 20, 22)")
    parser.add_argument("--dry-run", action="store_true", help="実際には投稿せず内容だけ表示")
    args = parser.parse_args()

    hour = args.hour or datetime.datetime.now().strftime("%H")

    logger.info("=== X自動投稿 開始 (時間帯: %s時) ===", hour)

    # コンテンツ生成
    try:
        from claude_generator import generate_x_post, load_history, record_x_post
        result = generate_x_post(hour)
    except Exception as e:
        logger.error("コンテンツ生成失敗: %s", e)
        from notify import notify_error
        notify_error("post_x.py / コンテンツ生成", str(e))
        sys.exit(1)

    theme = result["theme"]
    content = result["content"]
    hashtags = result.get("hashtags", [])
    full_post = result.get("full_post", content)
    hook_id = result.get("hook_id", "")
    engagement_type = result.get("engagement_type", "informational")
    char_count = len(full_post)

    logger.info("テーマ: %s", theme)
    logger.info("ハッシュタグ: %s", " ".join(hashtags))
    logger.info("文字数: %d文字", char_count)
    logger.info("内容:\n%s", full_post)

    if char_count > 140:
        logger.warning("文字数超過 (%d文字)。trim_to_fit で調整します。", char_count)
        from claude_generator import trim_to_fit
        content, hashtags = trim_to_fit(content, hashtags, limit=140)
        full_post = f"{content}\n{' '.join(hashtags)}"
        char_count = len(full_post)
        logger.info("調整後: %d文字", char_count)

    # Slack通知（投稿文生成完了）
    from config import TIME_SLOTS
    from notify import notify_x_post
    time_label = TIME_SLOTS.get(hour, f"{hour}時台")
    notify_x_post(time_label, full_post, char_count, hashtags)

    if args.dry_run:
        logger.info("【DRY RUN】実際の投稿はスキップします。")
        try:
            from sheets_logger import append_x_post
            append_x_post(full_post, hour, posted=False)
        except Exception as e:
            logger.warning("スプレッドシート書き込みエラー (dry-run): %s", e)
        return

    # X投稿
    try:
        from x_poster import post_tweet
        tweet_id = post_tweet(full_post)
    except Exception as e:
        logger.error("投稿失敗: %s", e)
        from notify import notify_error
        notify_error("post_x.py / X投稿", str(e))
        sys.exit(1)

    if tweet_id is None:
        logger.error("投稿に失敗しました。")
        from notify import notify_error
        notify_error("post_x.py / X投稿", "tweet_idがNullでした。API応答を確認してください。")
        sys.exit(1)

    # 履歴に記録
    history = load_history()
    record_x_post(history, theme, full_post, tweet_id, hook_id, engagement_type)

    # スプレッドシートに記録（投稿済み=True）
    try:
        from sheets_logger import append_x_post
        append_x_post(full_post, hour, posted=True)
    except Exception as e:
        logger.warning("スプレッドシート書き込みエラー: %s", e)

    logger.info("=== 完了 | tweet_id: %s ===", tweet_id)


if __name__ == "__main__":
    main()
