import time
import urllib.parse
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from selenium import webdriver
from .utils import setup_logger, random_sleep, load_done_ids, save_done_ids

logger = setup_logger("like_bot")

SEARCH_QUERIES = [
    "副業 稼ぐ",
    "副業 始め方",
    "転職 北海道",
    "北海道 副業",
    "在宅ワーク 北海道",
    "副業 会社員",
    "転職活動 体験談",
    "北海道 移住 仕事",
    "フリーランス 北海道",
    "副業 収入",
]


def search_and_like(driver: webdriver.Chrome, query: str, target: int, done_ids: set) -> int:
    liked = 0
    encoded = urllib.parse.quote(query)
    url = f"https://x.com/search?q={encoded}&src=typed_query&f=live"
    driver.get(url)
    time.sleep(4)

    scrolls = 0
    while liked < target and scrolls < 10:
        tweets = driver.find_elements(By.CSS_SELECTOR, 'article[data-testid="tweet"]')

        for tweet in tweets:
            if liked >= target:
                break
            try:
                # ツイートIDを一意キーとして取得
                link = tweet.find_element(By.CSS_SELECTOR, 'a[href*="/status/"]')
                tweet_id = link.get_attribute("href").split("/status/")[1].split("?")[0]

                if tweet_id in done_ids:
                    continue

                like_btn = tweet.find_element(By.CSS_SELECTOR, '[data-testid="like"]')
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", like_btn)
                random_sleep(0.5, 1.0)
                like_btn.click()
                random_sleep(3, 8)

                done_ids.add(tweet_id)
                liked += 1
                logger.info(f"いいね [{liked}/{target}] tweet_id={tweet_id} query={query}")

            except Exception as e:
                logger.debug(f"スキップ: {e}")
                continue

        # スクロールして追加読み込み
        driver.execute_script("window.scrollBy(0, 1200);")
        time.sleep(3)
        scrolls += 1

    return liked


def run(driver: webdriver.Chrome, daily_limit: int = 50) -> None:
    logger.info(f"いいねBot開始 / 目標: {daily_limit}件")
    done_ids = load_done_ids("like")
    already_done = len(done_ids)

    if already_done >= daily_limit:
        logger.info(f"本日分完了済み ({already_done}件)")
        return

    remaining = daily_limit - already_done
    per_query = max(1, remaining // len(SEARCH_QUERIES))
    total_liked = 0

    for query in SEARCH_QUERIES:
        if total_liked >= remaining:
            break
        count = min(per_query, remaining - total_liked)
        liked = search_and_like(driver, query, count, done_ids)
        total_liked += liked
        save_done_ids("like", done_ids)
        logger.info(f"クエリ「{query}」完了: {liked}件")
        random_sleep(10, 20)

    logger.info(f"いいねBot終了 / 本日合計: {already_done + total_liked}件")
