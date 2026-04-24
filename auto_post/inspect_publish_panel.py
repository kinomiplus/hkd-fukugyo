#!/usr/bin/env python3
"""
note.comの「公開に進む」後のパネルを調査する。
"""
import json
import subprocess
import sys
import time
import glob as _glob
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from config import NOTE_EMAIL, NOTE_PASSWORD, LOG_DIR, COOKIES_FILE

NOTE_URL = "https://note.com"
NOTE_LOGIN_URL = "https://note.com/login"
NOTE_NEW_URL = "https://note.com/notes/new"


def get_driver(headless=True):
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    patterns = [
        "/Users/yamaken/.wdm/drivers/chromedriver/mac64/*/chromedriver-mac-arm64/chromedriver",
        "/Users/yamaken/.wdm/drivers/chromedriver/mac64/*/chromedriver",
    ]
    candidates = []
    for pat in patterns:
        candidates.extend(_glob.glob(pat))
    if candidates:
        candidates.sort(reverse=True)
        driver_path = candidates[0]
    else:
        driver_path = ChromeDriverManager().install()

    service = Service(driver_path)
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


def save_state(driver, name):
    ts = int(time.time())
    png_path = LOG_DIR / f"panel_{name}_{ts}.png"
    html_path = LOG_DIR / f"panel_{name}_{ts}.html"
    driver.save_screenshot(str(png_path))
    html_path.write_text(driver.page_source, encoding="utf-8")
    print(f"[SAVED] {png_path}")
    return png_path


def login(driver):
    wait = WebDriverWait(driver, 30)
    if COOKIES_FILE.exists():
        driver.get(NOTE_URL)
        time.sleep(2)
        cookies = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
        for c in cookies:
            try:
                driver.add_cookie(c)
            except Exception:
                pass
        driver.refresh()
        time.sleep(3)
        if "login" not in driver.current_url:
            print("[INFO] クッキーでログイン成功")
            return True

    print("[INFO] メール/パスワードでログイン中...")
    driver.get(NOTE_LOGIN_URL)
    time.sleep(2)
    email_input = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email'], input[name='email']"))
    )
    email_input.clear()
    email_input.send_keys(NOTE_EMAIL)
    time.sleep(0.5)
    pwd_input = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
    pwd_input.clear()
    pwd_input.send_keys(NOTE_PASSWORD)
    time.sleep(0.5)
    pwd_input.send_keys(Keys.RETURN)
    time.sleep(5)
    if "login" in driver.current_url:
        print("[ERROR] ログイン失敗")
        return False
    cookies = driver.get_cookies()
    COOKIES_FILE.write_text(json.dumps(cookies, ensure_ascii=False), encoding="utf-8")
    print("[INFO] ログイン成功")
    return True


def copy_to_clipboard(text):
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)


def paste(driver):
    ActionChains(driver).key_down(Keys.COMMAND).send_keys("v").key_up(Keys.COMMAND).perform()
    time.sleep(1)


def main():
    headless = "--no-headless" not in sys.argv
    driver = get_driver(headless=headless)
    wait = WebDriverWait(driver, 30)

    try:
        if not login(driver):
            sys.exit(1)

        driver.get(NOTE_NEW_URL)
        time.sleep(5)
        print(f"[URL] エディタ: {driver.current_url}")

        # タイトル入力
        title_el = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "textarea[placeholder='記事タイトル']"))
        )
        title_el.click()
        time.sleep(0.3)
        title_el.clear()
        title_el.send_keys("テスト記事タイトル（検査用）")
        time.sleep(0.5)

        # 本文入力
        body_el = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".ProseMirror"))
        )
        body_el.click()
        time.sleep(0.3)
        copy_to_clipboard("これはnote.comエディタの検査用テスト本文です。")
        paste(driver)
        time.sleep(1)

        save_state(driver, "01_after_input")
        print(f"[STATE] タイトル・本文入力後: {driver.current_url}")

        # 「公開に進む」クリック
        buttons = driver.find_elements(By.CSS_SELECTOR, "button")
        publish_btn = None
        for btn in buttons:
            try:
                if "公開に進む" in btn.text and btn.is_displayed() and btn.is_enabled():
                    publish_btn = btn
                    break
            except Exception:
                pass

        if not publish_btn:
            print("[ERROR] 「公開に進む」ボタンが見つかりません")
            save_state(driver, "02_no_publish_btn")
            return

        print(f"[INFO] 「公開に進む」をクリック: '{publish_btn.text}'")
        driver.execute_script("arguments[0].click();", publish_btn)
        time.sleep(3)

        save_state(driver, "02_after_publish_click")
        print(f"[STATE] 「公開に進む」クリック後: {driver.current_url}")

        # パネル内のボタンを列挙
        print("\n[INSPECT] 公開パネルのボタン:")
        buttons = driver.find_elements(By.CSS_SELECTOR, "button")
        for i, btn in enumerate(buttons):
            try:
                txt = btn.text.strip()
                cls = btn.get_attribute("class") or ""
                visible = btn.is_displayed()
                enabled = btn.is_enabled()
                if visible:
                    print(f"  [{i}] text='{txt[:50]}' enabled={enabled} class={cls[:80]}")
            except Exception as e:
                print(f"  [{i}] ERROR: {e}")

        # dialog / modal 要素
        print("\n[INSPECT] ダイアログ・モーダル:")
        for sel in ["dialog", "[role='dialog']", "[class*='modal']", "[class*='Modal']",
                    "[class*='panel']", "[class*='Panel']", "[class*='drawer']", "[class*='Drawer']",
                    "[class*='sheet']", "[class*='Sheet']"]:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                try:
                    cls = el.get_attribute("class") or ""
                    visible = el.is_displayed()
                    if visible:
                        print(f"  sel='{sel}' class={cls[:100]}")
                        inner = el.get_attribute("innerHTML") or ""
                        print(f"    HTML: {inner[:500]}")
                except Exception:
                    pass

        # 「投稿する」「今すぐ公開」などのボタン候補
        print("\n[INSPECT] 公開確定ボタン候補:")
        for keyword in ["投稿する", "今すぐ公開", "公開する", "publish", "submit"]:
            els = driver.find_elements(By.XPATH, f"//*[contains(., '{keyword}')]")
            for el in els:
                try:
                    if el.is_displayed():
                        tag = el.tag_name
                        cls = el.get_attribute("class") or ""
                        txt = el.text.strip()
                        print(f"  keyword='{keyword}' tag={tag} text='{txt[:50]}' class={cls[:80]}")
                except Exception:
                    pass

        # パネル全体HTML
        print("\n[INSPECT] パネルHTML（先頭5000文字）:")
        body_inner = driver.find_element(By.TAG_NAME, "body").get_attribute("innerHTML")
        print(body_inner[:5000])

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
