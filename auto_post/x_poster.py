"""X (Twitter) API v2 を使って投稿するクライアント"""
import logging
import time
import tweepy
from config import X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET

logger = logging.getLogger(__name__)


def get_client() -> tweepy.Client:
    """tweepy v4 クライアントを返す（OAuth 1.0a User Context）"""
    return tweepy.Client(
        consumer_key=X_API_KEY,
        consumer_secret=X_API_SECRET,
        access_token=X_ACCESS_TOKEN,
        access_token_secret=X_ACCESS_TOKEN_SECRET,
    )


def post_tweet(content: str, retry: int = 3) -> str | None:
    """
    Xに投稿する。成功したらtweetIDを返す。
    レート制限時は待機してリトライする。
    """
    client = get_client()

    for attempt in range(1, retry + 1):
        try:
            response = client.create_tweet(text=content)
            tweet_id = str(response.data["id"])
            logger.info("投稿成功 | ID: %s | %s…", tweet_id, content[:30])
            return tweet_id

        except tweepy.errors.TooManyRequests as e:
            wait = 60 * attempt
            logger.warning("レート制限 (試行 %d/%d)。%d秒待機します。", attempt, retry, wait)
            time.sleep(wait)

        except tweepy.errors.Forbidden as e:
            logger.error("権限エラー: %s", e)
            logger.error("X Developer PortalでRead and Write権限を確認してください。")
            return None

        except tweepy.errors.Unauthorized as e:
            logger.error("認証エラー: %s", e)
            logger.error(".envのX API認証情報を確認してください。")
            return None

        except Exception as e:
            logger.error("予期しないエラー (試行 %d/%d): %s", attempt, retry, e)
            if attempt < retry:
                time.sleep(10)

    logger.error("投稿失敗: %d回試行しましたが全て失敗しました。", retry)
    return None
