import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from selenium import webdriver
from .browser import wait_for, save_cookies, load_cookies
from .utils import setup_logger, random_sleep

logger = setup_logger("auth")


def is_logged_in(driver: webdriver.Chrome) -> bool:
    try:
        driver.get("https://x.com/home")
        time.sleep(3)
        return "home" in driver.current_url
    except Exception:
        return False


def login(driver: webdriver.Chrome, username: str, password: str, email: str = "") -> bool:
    # Try cookies first
    if load_cookies(driver):
        if is_logged_in(driver):
            logger.info("クッキーでログイン成功")
            return True

    logger.info("パスワードでログイン開始")
    driver.get("https://x.com/i/flow/login")
    time.sleep(3)

    try:
        # Step 1: username/email
        user_input = wait_for(driver, By.CSS_SELECTOR, 'input[autocomplete="username"]')
        user_input.click()
        random_sleep(0.5, 1.2)
        user_input.send_keys(username)
        random_sleep(0.8, 1.5)
        next_btns = driver.find_elements(By.XPATH, "//button[contains(., '次へ')]")
        if next_btns:
            next_btns[0].click()
        else:
            user_input.send_keys(Keys.RETURN)
        random_sleep(0.8, 1.5)
        random_sleep(2, 3)

        # Step 2: unusual activity check (phone/email verification)
        try:
            verify_input = driver.find_element(By.CSS_SELECTOR, 'input[data-testid="ocfEnterTextTextInput"]')
            logger.info("追加認証が必要です。メール/電話番号を入力します")
            verify_input.send_keys(email or username)
            random_sleep(0.8, 1.5)
            verify_input.send_keys(Keys.RETURN)
            random_sleep(2, 3)
        except Exception:
            pass

        # Step 3: password
        pwd_input = wait_for(driver, By.CSS_SELECTOR, 'input[name="password"]')
        pwd_input.click()
        random_sleep(0.5, 1.0)
        pwd_input.send_keys(password)
        random_sleep(0.8, 1.5)
        pwd_input.send_keys(Keys.RETURN)
        random_sleep(4, 6)

        if is_logged_in(driver):
            save_cookies(driver)
            logger.info("ログイン成功・クッキー保存")
            return True
        else:
            logger.error(f"ログイン失敗: {driver.current_url}")
            return False

    except Exception as e:
        logger.error(f"ログインエラー: {e}")
        return False
