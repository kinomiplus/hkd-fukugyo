import time
import urllib.parse
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

import anthropic
from selenium import webdriver
from .utils import setup_logger, random_sleep, load_done_ids, save_done_ids

logger = setup_logger("reply_bot")

SEARCH_QUERIES = [
    "副業 始めた",
    "転職 北海道 悩み",
    "副業 収入 月",
    "在宅ワーク 始めたい",
    "北海道 副業 おすすめ",
]

SYSTEM_PROMPT = """あなたは「北海道副業ナビ」として、北海道在住の会社員に向けて副業・転職情報を発信しています。

キャラクター設定:
- 一人称: ぼく
- トンマナ: 親しみやすくリアル。北海道在住のリアルな体験談ベースで語る
- 宣伝臭は禁止。自然な共感や応援のリプライを送る

リプライのルール:
- 80字以内で簡潔に
- ハッシュタグ・絵文字は使わない
- 相手の投稿に共感し、一言アドバイスまたは体験談を添える
- 「ぼくも〜」「北海道だと〜」「〜だよね」などの自然な語り口
- リンクや宣伝は絶対に含めない
"""


def generate_reply(client: anthropic.Anthropic, tweet_text: str) -> str:
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"以下のツイートに自然なリプライを1つだけ生成してください（80字以内）:\n\n{tweet_text}",
            }
        ],
    )
    return message.content[0].text.strip()


def post_reply(driver: webdriver.Chrome, tweet: object, reply_text: str) -> bool:
    try:
        reply_btn = tweet.find_element(By.CSS_SELECTOR, '[data-testid="reply"]')
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", reply_btn)
        random_sleep(0.5, 1.0)
        reply_btn.click()
        random_sleep(2, 3)

        # リプライダイアログのテキストエリア
        text_area = driver.find_element(By.CSS_SELECTOR, '[data-testid="tweetTextarea_0"]')
        text_area.click()
        random_sleep(0.5, 1.0)
        text_area.send_keys(reply_text)
        random_sleep(1.5, 2.5)

        # 送信ボタン
        send_btn = driver.find_element(By.CSS_SELECTOR, '[data-testid="tweetButtonInline"]')
        send_btn.click()
        random_sleep(3, 5)
        return True

    except Exception as e:
        logger.error(f"リプライ送信エラー: {e}")
        # ダイアログを閉じる試み
        try:
            driver.find_element(By.CSS_SELECTOR, '[data-testid="app-bar-close"]').click()
        except Exception:
            pass
        return False


def search_and_reply(
    driver: webdriver.Chrome,
    client: anthropic.Anthropic,
    query: str,
    target: int,
    done_ids: set,
) -> int:
    replied = 0
    encoded = urllib.parse.quote(query)
    url = f"https://x.com/search?q={encoded}&src=typed_query&f=live"
    driver.get(url)
    time.sleep(4)

    scrolls = 0
    while replied < target and scrolls < 10:
        tweets = driver.find_elements(By.CSS_SELECTOR, 'article[data-testid="tweet"]')

        for tweet in tweets:
            if replied >= target:
                break
            try:
                link = tweet.find_element(By.CSS_SELECTOR, 'a[href*="/status/"]')
                tweet_id = link.get_attribute("href").split("/status/")[1].split("?")[0]

                if tweet_id in done_ids:
                    continue

                # ツイート本文を取得
                try:
                    text_el = tweet.find_element(By.CSS_SELECTOR, '[data-testid="tweetText"]')
                    tweet_text = text_el.text
                except Exception:
                    continue

                if not tweet_text or len(tweet_text) < 10:
                    continue

                logger.info(f"リプライ生成中: {tweet_text[:50]}...")
                reply_text = generate_reply(client, tweet_text)
                logger.info(f"生成リプライ: {reply_text}")

                success = post_reply(driver, tweet, reply_text)
                if success:
                    done_ids.add(tweet_id)
                    replied += 1
                    logger.info(f"リプライ送信 [{replied}/{target}] tweet_id={tweet_id}")
                    random_sleep(10, 30)

            except Exception as e:
                logger.debug(f"スキップ: {e}")
                continue

        driver.execute_script("window.scrollBy(0, 1200);")
        time.sleep(3)
        scrolls += 1

    return replied


def run(driver: webdriver.Chrome, api_key: str, daily_limit: int = 10) -> None:
    logger.info(f"リプライBot開始 / 目標: {daily_limit}件")
    done_ids = load_done_ids("reply")
    already_done = len(done_ids)

    if already_done >= daily_limit:
        logger.info(f"本日分完了済み ({already_done}件)")
        return

    client = anthropic.Anthropic(api_key=api_key)
    remaining = daily_limit - already_done
    total_replied = 0

    for query in SEARCH_QUERIES:
        if total_replied >= remaining:
            break
        count = min(2, remaining - total_replied)
        replied = search_and_reply(driver, client, query, count, done_ids)
        total_replied += replied
        save_done_ids("reply", done_ids)
        logger.info(f"クエリ「{query}」完了: {replied}件")
        random_sleep(20, 40)

    logger.info(f"リプライBot終了 / 本日合計: {already_done + total_replied}件")
