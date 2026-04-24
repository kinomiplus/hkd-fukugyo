import pickle
import re
import subprocess
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

COOKIE_PATH = Path(__file__).parent / "data" / "cookies.pkl"


def _chrome_major_version() -> int:
    try:
        result = subprocess.run(
            ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        m = re.search(r"(\d+)\.", result.stdout)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return 0


def create_driver(headless: bool = True) -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--lang=ja-JP")
    options.add_argument("--window-size=1280,900")
    if headless:
        options.add_argument("--headless=new")

    version = _chrome_major_version() or None
    return webdriver.Chrome(options=options)


def wait_for(driver: webdriver.Chrome, by: str, selector: str, timeout: int = 15):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((by, selector))
    )


def save_cookies(driver: webdriver.Chrome) -> None:
    COOKIE_PATH.parent.mkdir(exist_ok=True)
    with open(COOKIE_PATH, "wb") as f:
        pickle.dump(driver.get_cookies(), f)


def load_cookies(driver: webdriver.Chrome) -> bool:
    if not COOKIE_PATH.exists():
        return False
    driver.get("https://x.com")
    time.sleep(2)
    with open(COOKIE_PATH, "rb") as f:
        cookies = pickle.load(f)
    for cookie in cookies:
        try:
            driver.add_cookie(cookie)
        except Exception:
            pass
    driver.refresh()
    time.sleep(3)
    return True
