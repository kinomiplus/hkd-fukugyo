#!/usr/bin/env python3
"""
note.comエディタのHTML要素を調査するスクリプト。
実行後 logs/inspect_*.png と logs/inspect_*.html が生成される。
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
    png_path = LOG_DIR / f"inspect_{name}_{ts}.png"
    html_path = LOG_DIR / f"inspect_{name}_{ts}.html"
    driver.save_screenshot(str(png_path))
    html_path.write_text(driver.page_source, encoding="utf-8")
    print(f"[SAVED] {png_path}")
    print(f"[SAVED] {html_path}")
    return png_path, html_path


def login(driver):
    wait = WebDriverWait(driver, 30)

    # まずクッキーを試す
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
    save_state(driver, "01_login_page")

    email_input = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR,
            "input[type='email'], input[name='email'], input[placeholder*='mail']"))
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
        save_state(driver, "01_login_failed")
        print("[ERROR] ログイン失敗")
        return False

    cookies = driver.get_cookies()
    COOKIES_FILE.write_text(json.dumps(cookies, ensure_ascii=False), encoding="utf-8")
    print("[INFO] ログイン成功・クッキー保存")
    return True


def inspect_editor(driver):
    wait = WebDriverWait(driver, 30)

    print(f"\n[STEP] エディタへ遷移: {NOTE_NEW_URL}")
    driver.get(NOTE_NEW_URL)
    time.sleep(5)
    print(f"[URL] {driver.current_url}")
    save_state(driver, "02_editor_initial")

    # contenteditable 要素をすべて列挙
    print("\n[INSPECT] contenteditable要素:")
    elements = driver.find_elements(By.CSS_SELECTOR, "[contenteditable]")
    for i, el in enumerate(elements):
        try:
            tag = el.tag_name
            cls = el.get_attribute("class") or ""
            ph = el.get_attribute("data-placeholder") or ""
            aria = el.get_attribute("aria-label") or ""
            role = el.get_attribute("role") or ""
            visible = el.is_displayed()
            print(f"  [{i}] tag={tag} class={cls[:80]} placeholder={ph[:40]} "
                  f"aria={aria[:40]} role={role} visible={visible}")
        except Exception as e:
            print(f"  [{i}] ERROR: {e}")

    # textarea 要素
    print("\n[INSPECT] textarea要素:")
    textareas = driver.find_elements(By.CSS_SELECTOR, "textarea")
    for i, el in enumerate(textareas):
        try:
            ph = el.get_attribute("placeholder") or ""
            cls = el.get_attribute("class") or ""
            visible = el.is_displayed()
            print(f"  [{i}] placeholder={ph[:60]} class={cls[:80]} visible={visible}")
        except Exception as e:
            print(f"  [{i}] ERROR: {e}")

    # input 要素（text系）
    print("\n[INSPECT] input[type=text]要素:")
    inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input:not([type])")
    for i, el in enumerate(inputs):
        try:
            ph = el.get_attribute("placeholder") or ""
            cls = el.get_attribute("class") or ""
            name = el.get_attribute("name") or ""
            visible = el.is_displayed()
            print(f"  [{i}] placeholder={ph[:60]} name={name} class={cls[:80]} visible={visible}")
        except Exception as e:
            print(f"  [{i}] ERROR: {e}")

    # ボタン一覧
    print("\n[INSPECT] ボタン要素:")
    buttons = driver.find_elements(By.CSS_SELECTOR, "button")
    for i, el in enumerate(buttons):
        try:
            txt = el.text.strip()
            cls = el.get_attribute("class") or ""
            visible = el.is_displayed()
            enabled = el.is_enabled()
            if visible:
                print(f"  [{i}] text='{txt[:40]}' class={cls[:80]} enabled={enabled}")
        except Exception as e:
            print(f"  [{i}] ERROR: {e}")

    # ProseMirror 確認
    print("\n[INSPECT] ProseMirror:")
    pm = driver.find_elements(By.CSS_SELECTOR, ".ProseMirror")
    for i, el in enumerate(pm):
        try:
            cls = el.get_attribute("class") or ""
            visible = el.is_displayed()
            print(f"  [{i}] class={cls[:100]} visible={visible}")
        except Exception as e:
            print(f"  [{i}] ERROR: {e}")

    # エディタ内部構造を取得
    print("\n[INSPECT] エディタルート:")
    editor_roots = driver.find_elements(By.CSS_SELECTOR,
        "[class*='editor'], [class*='Editor'], [class*='noteEditor'], [class*='NoteEditor']")
    for i, el in enumerate(editor_roots[:5]):
        try:
            tag = el.tag_name
            cls = el.get_attribute("class") or ""
            visible = el.is_displayed()
            print(f"  [{i}] tag={tag} class={cls[:100]} visible={visible}")
        except Exception as e:
            print(f"  [{i}] ERROR: {e}")

    # タイトル周辺を重点的に探す
    print("\n[INSPECT] タイトル候補:")
    for sel in [
        "textarea[placeholder*='タイトル']",
        "input[placeholder*='タイトル']",
        "[data-placeholder*='タイトル']",
        "[aria-label*='タイトル']",
        "[class*='title']",
        "[class*='Title']",
        "h1[contenteditable]",
    ]:
        els = driver.find_elements(By.CSS_SELECTOR, sel)
        for el in els:
            try:
                tag = el.tag_name
                cls = el.get_attribute("class") or ""
                ph = el.get_attribute("placeholder") or el.get_attribute("data-placeholder") or ""
                visible = el.is_displayed()
                print(f"  sel='{sel}' tag={tag} class={cls[:80]} ph={ph[:40]} visible={visible}")
            except Exception:
                pass

    # ページ上部のHTML構造（body直下）
    print("\n[INSPECT] ページ上部HTML（先頭3000文字）:")
    body_html = driver.find_element(By.TAG_NAME, "body").get_attribute("innerHTML")
    print(body_html[:3000])

    # エディタ固有構造
    print("\n[INSPECT] エディタ固有HTML（先頭5000文字）:")
    for sel in ["[class*='editorArea'], [class*='EditorArea'], main, article, [role='main']"]:
        els = driver.find_elements(By.CSS_SELECTOR, sel)
        if els:
            inner = els[0].get_attribute("innerHTML") or ""
            print(f"sel={sel}: {inner[:5000]}")
            break

    save_state(driver, "03_editor_inspected")
    print("\n[INFO] 検査完了")


def main():
    headless = "--no-headless" not in sys.argv
    print(f"[INFO] headless={headless}")
    driver = get_driver(headless=headless)
    try:
        if not login(driver):
            sys.exit(1)
        inspect_editor(driver)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
