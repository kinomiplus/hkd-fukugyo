#!/usr/bin/env python3
"""
日次完了レポートをSlackに送信するスクリプト
cron: 毎日 22:30 に実行
"""
import datetime
import json
import logging
import sys
from pathlib import Path

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
today_str = datetime.date.today().strftime("%Y%m%d")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"report_{today_str}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

HISTORY_FILE = Path(__file__).parent / "post_history.json"


def count_today_posts() -> tuple[int, int]:
    if not HISTORY_FILE.exists():
        return 0, 0
    history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    today = datetime.date.today().isoformat()
    x_count = sum(
        1 for p in history.get("x_posts", [])
        if p.get("date", "").startswith(today)
    )
    note_count = sum(
        1 for a in history.get("note_articles", [])
        if a.get("date", "").startswith(today)
    )
    return x_count, note_count


def count_today_errors() -> int:
    log_file = LOG_DIR / f"x_{today_str}.log"
    if not log_file.exists():
        return 0
    text = log_file.read_text(encoding="utf-8", errors="ignore")
    return text.count("[ERROR]")


def main() -> None:
    logger.info("=== 日次レポート送信 ===")
    x_count, note_count = count_today_posts()
    error_count = count_today_errors()

    from notify import notify_daily_report
    notify_daily_report(x_count, note_count, error_count)

    logger.info("X投稿: %d件 / note投稿: %d件 / エラー: %d件", x_count, note_count, error_count)
    logger.info("=== 完了 ===")


if __name__ == "__main__":
    main()
