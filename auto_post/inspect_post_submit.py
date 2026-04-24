#!/usr/bin/env python3
"""
「投稿する」クリック後のURL遷移を調査する。
"""
import json
import sys
import time
import glob as _glob
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from config import NOTE_EMAIL, NOTE_PASSWORD, LOG_DIR, COOKIES_FILE

NOTE_URL = "https://note.com"
NOTE_NEW_URL = "https://note.com/notes/new"
NOTE_LOGIN_URL = "https://note.com/login"


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
    png = LOG_DIR / f"ps_{name}_{ts}.png"
    html = LOG_DIR / f"ps_{name}_{ts}.html"
    driver.save_screenshot(str(png))
    html.write_text(driver.page_source, encoding="utf-8")
    print(f"[SAVED] {png}")


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
            print("[INFO] クッキーログイン成功")
            return True
    driver.get(NOTE_LOGIN_URL)
    time.sleep(2)
    email_input = wait.until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, "input[type='email']")))
    email_input.clear()
    email_input.send_keys(NOTE_EMAIL)
    pwd = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
    pwd.clear()
    pwd.send_keys(NOTE_PASSWORD)
    pwd.send_keys(Keys.RETURN)
    time.sleep(5)
    if "login" in driver.current_url:
        print("[ERROR] ログイン失敗")
        return False
    COOKIES_FILE.write_text(json.dumps(driver.get_cookies(), ensure_ascii=False))
    print("[INFO] ログイン成功")
    return True


def react_set_textarea(driver, element, value):
    driver.execute_script("""
        var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
            window.HTMLTextAreaElement.prototype, 'value'
        ).set;
        nativeInputValueSetter.call(arguments[0], arguments[1]);
        arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
        arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
    """, element, value)


def prosemirror_paste(driver, element, text):
    driver.execute_script("""
        var el = arguments[0];
        var text = arguments[1];
        el.focus();
        var dt = new DataTransfer();
        dt.setData('text/plain', text);
        var event = new ClipboardEvent('paste', {
            clipboardData: dt,
            bubbles: true,
            cancelable: true
        });
        el.dispatchEvent(event);
    """, element, text)


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

        # タイトル
        title_el = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "textarea[placeholder='記事タイトル']")))
        react_set_textarea(driver, title_el, "検査用テスト記事（自動削除可）")
        time.sleep(0.5)

        # 本文
        body_el = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".ProseMirror")))
        prosemirror_paste(driver, body_el,
            "これは自動化テスト用の記事です。検査が完了したら削除してください。\n\n北海道副業ナビ自動投稿テスト。")
        time.sleep(1)

        # 「公開に進む」
        publish_btn = None
        for btn in driver.find_elements(By.CSS_SELECTOR, "button"):
            try:
                if "公開に進む" in btn.text and btn.is_displayed():
                    publish_btn = btn
                    break
            except Exception:
                pass
        if not publish_btn:
            print("[ERROR] 「公開に進む」が見つかりません")
            save_state(driver, "no_publish_btn")
            return
        print(f"[INFO] 「公開に進む」クリック (URL before: {driver.current_url})")
        driver.execute_script("arguments[0].click();", publish_btn)
        time.sleep(4)
        print(f"[URL] 公開設定画面: {driver.current_url}")
        save_state(driver, "publish_settings")

        # 「投稿する」
        post_btn = None
        for btn in driver.find_elements(By.CSS_SELECTOR, "button"):
            try:
                if btn.text.strip() == "投稿する" and btn.is_displayed():
                    post_btn = btn
                    break
            except Exception:
                pass
        if not post_btn:
            print("[ERROR] 「投稿する」が見つかりません")
            save_state(driver, "no_post_btn")
            return
        print(f"[INFO] 「投稿する」クリック (URL before: {driver.current_url})")
        driver.execute_script("arguments[0].click();", post_btn)

        # URL変化を最大30秒ポーリング
        print("[INFO] 公開後URL待機中...")
        for i in range(30):
            time.sleep(1)
            url = driver.current_url
            print(f"  [{i+1:02d}s] URL: {url}")
            if "editor.note.com" not in url and "note.com" in url:
                print(f"\n[SUCCESS] 公開URL確認: {url}")
                save_state(driver, "post_success")
                break
            if i == 9 or i == 19:
                save_state(driver, f"post_waiting_{i+1}s")
        else:
            print(f"\n[TIMEOUT] 30秒後の最終URL: {driver.current_url}")
            save_state(driver, "post_timeout")

        # リンク検索
        print("\n[INSPECT] /n/ を含むリンク:")
        for link in driver.find_elements(By.CSS_SELECTOR, "a[href*='/n/']"):
            href = link.get_attribute("href") or ""
            if "note.com" in href and "editor.note.com" not in href:
                print(f"  {href}")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
