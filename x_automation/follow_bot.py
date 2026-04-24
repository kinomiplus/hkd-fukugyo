import time
import urllib.parse
from selenium.webdriver.common.by import By

from selenium import webdriver
from .utils import setup_logger, random_sleep, load_done_ids, save_done_ids

logger = setup_logger("follow_bot")

SEARCH_QUERIES = [
    "副業 北海道",
    "転職 北海道",
    "在宅ワーク 北海道",
    "副業 会社員",
    "北海道 フリーランス",
    "副業 稼ぐ方法",
]


def search_and_follow(driver: webdriver.Chrome, query: str, target: int, done_ids: set) -> int:
    followed = 0
    encoded = urllib.parse.quote(query)
    url = f"https://x.com/search?q={encoded}&src=typed_query&f=user"
    driver.get(url)
    time.sleep(4)

    scrolls = 0
    while followed < target and scrolls < 8:
        cells = driver.find_elements(By.CSS_SELECTOR, '[data-testid="UserCell"]')

        for cell in cells:
            if followed >= target:
                break
            try:
                # ユーザー名をIDとして使用
                user_link = cell.find_element(By.CSS_SELECTOR, 'a[role="link"][href^="/"]')
                username = user_link.get_attribute("href").strip("/").split("/")[-1]

                if username in done_ids or username == "":
                    continue

                # フォローボタン（まだフォローしていない場合のみ）
                try:
                    follow_btn = cell.find_element(By.CSS_SELECTOR, '[data-testid$="-follow"]')
                    btn_text = follow_btn.text
                    if "フォロー中" in btn_text or "Following" in btn_text:
                        done_ids.add(username)
                        continue
                except Exception:
                    continue

                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", follow_btn)
                random_sleep(0.5, 1.0)
                follow_btn.click()
                random_sleep(5, 10)

                done_ids.add(username)
                followed += 1
                logger.info(f"フォロー [{followed}/{target}] @{username} query={query}")

            except Exception as e:
                logger.debug(f"スキップ: {e}")
                continue

        driver.execute_script("window.scrollBy(0, 1000);")
        time.sleep(3)
        scrolls += 1

    return followed


def run(driver: webdriver.Chrome, daily_limit: int = 20) -> None:
    logger.info(f"フォローBot開始 / 目標: {daily_limit}件")
    done_ids = load_done_ids("follow")
    already_done = len(done_ids)

    if already_done >= daily_limit:
        logger.info(f"本日分完了済み ({already_done}件)")
        return

    remaining = daily_limit - already_done
    per_query = max(1, remaining // len(SEARCH_QUERIES))
    total_followed = 0

    for query in SEARCH_QUERIES:
        if total_followed >= remaining:
            break
        count = min(per_query, remaining - total_followed)
        followed = search_and_follow(driver, query, count, done_ids)
        total_followed += followed
        save_done_ids("follow", done_ids)
        logger.info(f"クエリ「{query}」完了: {followed}件")
        random_sleep(15, 30)

    logger.info(f"フォローBot終了 / 本日合計: {already_done + total_followed}件")
