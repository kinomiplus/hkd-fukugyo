"""Slack Webhook通知ユーティリティ"""
import json
import logging
import urllib.request

logger = logging.getLogger(__name__)


def _send(text: str) -> bool:
    from config import SLACK_WEBHOOK_URL
    if not SLACK_WEBHOOK_URL:
        logger.warning("SLACK_WEBHOOK_URLが未設定のため通知をスキップします。")
        return False
    data = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(SLACK_WEBHOOK_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            if res.status == 200:
                logger.info("Slack通知送信成功")
                return True
            logger.warning("Slack通知応答: %s", res.status)
            return False
    except Exception as e:
        logger.warning("Slack通知送信失敗: %s", e)
        return False


def notify_x_post(time_label: str, full_post: str, char_count: int, hashtags: list[str]) -> None:
    text = (
        f"📱 *X投稿生成完了*\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"⏰ 投稿時間帯：{time_label}\n"
        f"📝 投稿内容：\n{full_post}\n\n"
        f"📊 文字数：{char_count}文字\n"
        f"🏷️ ハッシュタグ：{' '.join(hashtags)}"
    )
    _send(text)


def notify_note_posted(title: str, article_url: str, char_count: int) -> None:
    text = (
        f"📝 *note記事投稿完了*\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📌 タイトル：{title}\n"
        f"🔗 URL：{article_url}\n"
        f"📊 文字数：{char_count}文字"
    )
    _send(text)


def notify_error(source: str, message: str) -> None:
    text = (
        f"🚨 *エラー発生*\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"⚙️ 発生元：{source}\n"
        f"❌ 内容：{message}"
    )
    _send(text)


def notify_daily_report(x_count: int, note_count: int, errors: int = 0) -> None:
    status = "✅ 正常" if errors == 0 else f"⚠️ エラーあり（{errors}件）"
    text = (
        f"📊 *日次完了レポート*\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📱 X投稿数：{x_count}件\n"
        f"📝 note投稿数：{note_count}件\n"
        f"🔔 ステータス：{status}"
    )
    _send(text)
