#!/usr/bin/env python3
"""
React+ProseMirror対応の入力で公開パネルを調査する。
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
    png = LOG_DIR / f"p2_{name}_{ts}.png"
    html = LOG_DIR / f"p2_{name}_{ts}.html"
    driver.save_screenshot(str(png))
    html.write_text(driver.page_source, encoding="utf-8")
    print(f"[SAVED] {png}")
    return png


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
        (By.CSS_SELECTOR, "input[type='email'], input[name='email']")))
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
    """React管理のtextareaにネイティブプロパティ経由で値をセットする。"""
    driver.execute_script("""
        var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
            window.HTMLTextAreaElement.prototype, 'value'
        ).set;
        nativeInputValueSetter.call(arguments[0], arguments[1]);
        arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
        arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
    """, element, value)


def prosemirror_paste(driver, element, text):
    """ProseMirrorエディタにClipboardEventで本文を貼り付ける。"""
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
        print(f"[URL] {driver.current_url}")

        # タイトル入力 (React対応)
        title_el = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "textarea[placeholder='記事タイトル']"))
        )
        title_text = "テスト記事タイトル（検査用）"
        react_set_textarea(driver, title_el, title_text)
        time.sleep(0.5)

        # 確認
        actual_title = driver.execute_script("return arguments[0].value;", title_el)
        print(f"[CHECK] タイトル実際値: '{actual_title}'")

        # 本文入力 (ProseMirror ClipboardEvent)
        body_el = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".ProseMirror"))
        )
        body_text = "これはnote.comエディタの検査用テスト本文です。北海道副業ナビのテスト投稿。"
        prosemirror_paste(driver, body_el, body_text)
        time.sleep(1)

        # 本文確認
        actual_body = driver.execute_script("return arguments[0].innerText;", body_el)
        print(f"[CHECK] 本文実際値: '{actual_body[:80]}'")

        save_state(driver, "01_after_js_input")

        # 「公開に進む」クリック
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
            save_state(driver, "02_no_btn")
            return

        print(f"[INFO] 「公開に進む」クリック")
        driver.execute_script("arguments[0].click();", publish_btn)
        time.sleep(4)

        save_state(driver, "02_after_publish_click")
        print(f"[URL] {driver.current_url}")

        # 現れたボタンをすべて列挙
        print("\n[INSPECT] クリック後のボタン一覧:")
        for i, btn in enumerate(driver.find_elements(By.CSS_SELECTOR, "button")):
            try:
                txt = btn.text.strip()
                visible = btn.is_displayed()
                enabled = btn.is_enabled()
                cls = (btn.get_attribute("class") or "")[:80]
                if visible and txt:
                    print(f"  [{i}] '{txt}' enabled={enabled} class={cls}")
            except Exception:
                pass

        # ダイアログ/モーダル
        print("\n[INSPECT] モーダル/ダイアログ:")
        for sel in ["[role='dialog']", ".ReactModal__Content", "[class*='Modal__content']"]:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                if el.is_displayed():
                    print(f"  sel={sel}")
                    print(f"  text: {el.text[:200]}")
                    print(f"  html: {(el.get_attribute('innerHTML') or '')[:500]}")

        # 公開パネル候補
        print("\n[INSPECT] 公開パネル候補:")
        for sel in [
            "[class*='publish']", "[class*='Publish']",
            "[class*='setting']", "[class*='Setting']",
            "[class*='modal']", "[class*='panel']",
        ]:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                if el.is_displayed():
                    cls = (el.get_attribute("class") or "")[:100]
                    txt = el.text[:100].strip()
                    if txt:
                        print(f"  sel={sel} class={cls}")
                        print(f"  text: {txt}")

        # URL変化確認
        print(f"\n[FINAL URL] {driver.current_url}")

        # 「投稿する」「今すぐ公開」含むXPath
        for kw in ["投稿する", "今すぐ公開", "公開する"]:
            found = driver.find_elements(By.XPATH, f"//button[contains(., '{kw}')]")
            for el in found:
                if el.is_displayed():
                    print(f"[FOUND] '{kw}' button: class={el.get_attribute('class')[:80]}")
                    print(f"  parent html: {(el.find_element(By.XPATH, '..').get_attribute('innerHTML') or '')[:300]}")

        # ページ変化を待つ（公開パネルが遅延ロードの可能性）
        print("\n[WAIT] 3秒追加待機して再確認...")
        time.sleep(3)
        save_state(driver, "03_after_wait")

        for kw in ["投稿する", "今すぐ公開", "公開する", "閉じる"]:
            found = driver.find_elements(By.XPATH, f"//button[contains(., '{kw}')]")
            for el in found:
                if el.is_displayed():
                    print(f"[FOUND after wait] '{kw}' button")

        # 公開パネルのHTML全体
        print("\n[HTML] body先頭8000文字:")
        print(driver.find_element(By.TAG_NAME, "body").get_attribute("innerHTML")[:8000])

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
