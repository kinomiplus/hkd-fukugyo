"""
note.com 自動投稿クライアント（v3 - 2026-04-24 要素確認済み）

【inspect_note_editor.py 実行で確認した要素】
  URL遷移: note.com/notes/new → editor.note.com/notes/{id}/edit/
  タイトル: textarea[placeholder='記事タイトル']  class=sc-80832eb4-0
  本文:     div.ProseMirror[role='textbox'][contenteditable='true']
  公開ボタン1: button text='公開に進む'  (右上)
  公開ボタン2: button text='投稿する'   (公開設定画面 右上)
  成功モーダル: .PublishedModal__content

【公開後のURL挙動】
  editor.note.com は公開後も自動でnote.comに遷移しない。
  /notes/{id}/publish/ URLから article_id を抽出し
  note.com/{user}/n/{id} を構築 → HTTP HEAD で疎通確認（最大5回）。

【公開フロー】
  1. note.com/notes/new → editor URLへ自動リダイレクト
  2. エディタURL から article_id を即時抽出
  3. タイトル入力（React native setter）
  4. 本文入力（ProseMirror ClipboardEvent → execCommand fallback）
  5. 「公開に進む」クリック → /publish/ URL遷移を確認
  6. 「投稿する」クリック → PublishedModal出現確認（最大5回リトライ）
  7. 公開URL (note.com/{user}/n/{id}) をHTTP確認、editor.note.comのままなら再試行
"""
import glob as _glob
import json
import logging
import re
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from config import NOTE_EMAIL, NOTE_PASSWORD, BASE_DIR, COOKIES_FILE

logger = logging.getLogger(__name__)

NOTE_URL        = "https://note.com"
NOTE_LOGIN_URL  = "https://note.com/login"
NOTE_NEW_URL    = "https://note.com/notes/new"
NOTE_USERNAME   = "hkd_fukugyo"
PUBLISH_VERIFY_RETRIES = 5


def _get_chromedriver_path() -> str:
    patterns = [
        "/Users/yamaken/.wdm/drivers/chromedriver/mac64/*/chromedriver-mac-arm64/chromedriver",
        "/Users/yamaken/.wdm/drivers/chromedriver/mac64/*/chromedriver",
    ]
    candidates = []
    for pat in patterns:
        candidates.extend(_glob.glob(pat))
    if candidates:
        candidates.sort(reverse=True)
        return candidates[0]
    return ChromeDriverManager().install()


class NotePoster:
    def __init__(self, headless: bool = True):
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

        service = Service(_get_chromedriver_path())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
        )
        self.wait = WebDriverWait(self.driver, 30)

    # ─── クッキー管理 ─────────────────────────────────────────

    def _save_cookies(self) -> None:
        cookies = self.driver.get_cookies()
        COOKIES_FILE.write_text(json.dumps(cookies, ensure_ascii=False), encoding="utf-8")
        logger.info("クッキー保存: %d件", len(cookies))

    def _load_cookies(self) -> bool:
        if not COOKIES_FILE.exists():
            return False
        try:
            self.driver.get(NOTE_URL)
            time.sleep(2)
            for cookie in json.loads(COOKIES_FILE.read_text(encoding="utf-8")):
                try:
                    self.driver.add_cookie(cookie)
                except Exception:
                    pass
            self.driver.refresh()
            time.sleep(3)
            return True
        except Exception as e:
            logger.warning("クッキー読み込み失敗: %s", e)
            return False

    def _is_logged_in(self) -> bool:
        try:
            els = self.driver.find_elements(
                By.CSS_SELECTOR,
                "a[href*='/notes/new'], [class*='userMenu'], [class*='UserMenu'], "
                "[data-test*='account'], button[aria-label*='アカウント']",
            )
            return len(els) > 0
        except Exception:
            return False

    # ─── ログイン ─────────────────────────────────────────────

    def login(self) -> bool:
        if self._load_cookies() and self._is_logged_in():
            logger.info("クッキーでログイン成功")
            return True
        return self._login_with_credentials()

    def _login_with_credentials(self) -> bool:
        logger.info("メール/パスワードでログイン中...")
        try:
            self.driver.get(NOTE_LOGIN_URL)
            time.sleep(2)
            email_el = self.wait.until(EC.presence_of_element_located((
                By.CSS_SELECTOR,
                "input[type='email'], input[name='email'], input[placeholder*='mail@example.com']",
            )))
            email_el.clear()
            email_el.send_keys(NOTE_EMAIL)
            time.sleep(0.5)

            pwd_el = self.driver.find_element(By.CSS_SELECTOR, "input[type='password']")
            pwd_el.clear()
            pwd_el.send_keys(NOTE_PASSWORD)
            time.sleep(0.5)
            pwd_el.send_keys(Keys.RETURN)
            time.sleep(5)

            if "login" not in self.driver.current_url:
                self._save_cookies()
                logger.info("ログイン成功")
                return True
            logger.error("ログイン失敗")
            self._screenshot("login_error")
            return False
        except Exception as e:
            logger.error("ログインエラー: %s", e)
            self._screenshot("login_error")
            return False

    # ─── JS入力ヘルパー ────────────────────────────────────────

    def _react_set_textarea(self, element, value: str) -> None:
        """React管理のtextareaにnative setterで値をセットする。"""
        self.driver.execute_script("""
            var setter = Object.getOwnPropertyDescriptor(
                window.HTMLTextAreaElement.prototype, 'value'
            ).set;
            setter.call(arguments[0], arguments[1]);
            arguments[0].dispatchEvent(new Event('input',  { bubbles: true }));
            arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
        """, element, value)

    def _prosemirror_insert(self, element, text: str) -> bool:
        """ProseMirrorにテキストを貼り付ける。
        ClipboardEvent → execCommand の順で試みる。成功したらTrue。"""
        # Method 1: ClipboardEvent paste（headlessで動作確認済み）
        try:
            self.driver.execute_script("""
                var el = arguments[0];
                var text = arguments[1];
                el.focus();
                var dt = new DataTransfer();
                dt.setData('text/plain', text);
                el.dispatchEvent(new ClipboardEvent('paste', {
                    clipboardData: dt, bubbles: true, cancelable: true
                }));
            """, element, text)
            time.sleep(0.8)
            actual = (self.driver.execute_script("return arguments[0].innerText;", element) or "").strip()
            if actual:
                return True
        except Exception as e:
            logger.warning("ClipboardEvent失敗: %s", e)

        # Method 2: execCommand insertText（ProseMirrorが受け付ける場合）
        try:
            self.driver.execute_script("""
                var el = arguments[0];
                var text = arguments[1];
                el.focus();
                document.execCommand('selectAll', false, null);
                document.execCommand('insertText', false, text);
            """, element, text)
            time.sleep(0.8)
            actual = (self.driver.execute_script("return arguments[0].innerText;", element) or "").strip()
            if actual:
                return True
        except Exception as e:
            logger.warning("execCommand失敗: %s", e)

        return False

    # ─── URL / 記事IDヘルパー ────────────────────────────────

    def _extract_article_id(self, url: str) -> str | None:
        """editor.note.com/notes/{id}/... から記事IDを取り出す（末尾スラッシュ不要）。"""
        m = re.search(r'/notes/([^/?#\s]+)', url)
        if m:
            cand = m.group(1)
            # 実際のnote IDは英数字のみ（ルートテンプレート[id]は除外）
            if re.match(r'^[a-z0-9]+$', cand) and len(cand) > 4:
                return cand
        return None

    def _build_published_url(self, article_id: str) -> str:
        return f"https://note.com/{NOTE_USERNAME}/n/{article_id}"

    # ─── モーダル検出 ────────────────────────────────────────

    def _is_published_modal_visible(self) -> bool:
        """「記事が公開されました」モーダルが画面に表示されているか確認する。"""
        try:
            # クラス名ベース
            for sel in [".PublishedModal__content", ".ReactModal__Content--after-open"]:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    if el.is_displayed():
                        return True
            # テキストベース（クラス名変更への保険）
            for el in self.driver.find_elements(By.XPATH, "//*[contains(., '記事が公開されました')]"):
                if el.is_displayed() and el.tag_name in ("h1", "h2", "p", "div", "span"):
                    return True
        except Exception:
            pass
        return False

    # ─── HTTP疎通確認 ────────────────────────────────────────

    def _verify_url_accessible(self, url: str, timeout: int = 10) -> bool:
        """URLが200系で応答するか確認する。"""
        try:
            req = urllib.request.Request(url, method="HEAD")
            req.add_header("User-Agent", "Mozilla/5.0")
            with urllib.request.urlopen(req, timeout=timeout) as res:
                return res.status < 400
        except Exception:
            return False

    # ─── ボタンユーティリティ ────────────────────────────────

    def _find_button_by_text(self, text: str):
        """完全一致テキストの表示・有効ボタンを返す。"""
        try:
            for btn in self.driver.find_elements(
                By.XPATH, f"//button[normalize-space(.)='{text}']"
            ):
                if btn.is_displayed() and btn.is_enabled():
                    return btn
        except Exception:
            pass
        return None

    def _wait_for_button(self, text: str, timeout: int = 15):
        deadline = time.time() + timeout
        while time.time() < deadline:
            btn = self._find_button_by_text(text)
            if btn:
                return btn
            time.sleep(1)
        return None

    # ─── 記事作成（メイン） ──────────────────────────────────

    def create_article(self, title: str, content: str) -> str | None:
        """
        note記事を作成・公開する。成功時は公開URLを返す。失敗時はNone。
        """
        logger.info("記事作成開始: %s", title[:40])

        try:
            # ── STEP 1: エディタへ遷移 ──────────────────────
            self.driver.get(NOTE_NEW_URL)
            # editor.note.com/notes/{id}/edit/ へのリダイレクトを待つ
            for _ in range(15):
                time.sleep(1)
                if "editor.note.com" in self.driver.current_url:
                    break

            current = self.driver.current_url
            logger.info("エディタURL: %s", current)

            if "login" in current:
                logger.warning("セッション切れ → 再ログイン中...")
                if not self._login_with_credentials():
                    logger.error("再ログイン失敗")
                    return None
                self.driver.get(NOTE_NEW_URL)
                for _ in range(15):
                    time.sleep(1)
                    if "editor.note.com" in self.driver.current_url:
                        break
                current = self.driver.current_url
                if "login" in current:
                    logger.error("再ログイン後もエディタにアクセスできない")
                    self._screenshot("session_recovery_failed")
                    return None

            # ── STEP 2: article_id を即時取得（遷移直後が最も確実） ──
            article_id = self._extract_article_id(self.driver.current_url)
            if article_id:
                logger.info("article_id 取得: %s", article_id)
            else:
                logger.warning("article_id を遷移直後のURLから取得できず: %s", self.driver.current_url)

            # ── STEP 3: タイトル入力 ────────────────────────
            try:
                title_el = self.wait.until(EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "textarea[placeholder='記事タイトル']")
                ))
            except Exception:
                logger.error("タイトルtextareaが見つかりません")
                self._screenshot("no_title_field")
                return None

            self._react_set_textarea(title_el, title)
            time.sleep(0.5)

            actual_title = (self.driver.execute_script("return arguments[0].value;", title_el) or "").strip()
            if actual_title != title.strip():
                logger.error("タイトル入力不一致: 期待=%r 実際=%r", title[:30], actual_title[:30])
                self._screenshot("title_mismatch")
                return None
            logger.info("タイトル入力完了: %s", title[:40])

            # ── STEP 4: 本文入力 ────────────────────────────
            try:
                body_el = self.wait.until(EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, ".ProseMirror")
                ))
            except Exception:
                logger.error("ProseMirrorが見つかりません")
                self._screenshot("no_body_field")
                return None

            if not self._prosemirror_insert(body_el, content):
                logger.error("本文入力に失敗（ClipboardEvent・execCommand 両方失敗）")
                self._screenshot("body_input_failed")
                return None

            actual_body = (self.driver.execute_script("return arguments[0].innerText;", body_el) or "").strip()
            if not actual_body:
                logger.error("本文が空のまま（入力されていない）")
                self._screenshot("body_empty")
                return None
            logger.info("本文入力完了: %d文字", len(content))

            # ── STEP 5: 「公開に進む」クリック ──────────────
            publish_btn = self._wait_for_button("公開に進む", timeout=10)
            if publish_btn is None:
                logger.error("「公開に進む」ボタンが見つかりません")
                self._screenshot("no_publish_button")
                return None

            logger.info("「公開に進む」クリック")
            self.driver.execute_script("arguments[0].click();", publish_btn)

            # /publish/ URLへの遷移を確認（最大15秒）
            publish_url_ok = False
            for _ in range(15):
                time.sleep(1)
                if "/publish" in self.driver.current_url:
                    publish_url_ok = True
                    break

            logger.info("公開設定画面URL: %s", self.driver.current_url)
            if not publish_url_ok:
                logger.warning("/publish URLへ遷移しませんでした（処理は続行）")

            # /publish/ URL から article_id を再抽出（より確実）
            id_from_publish = self._extract_article_id(self.driver.current_url)
            if id_from_publish:
                article_id = id_from_publish
                logger.info("article_id 再確認（publishURL）: %s", article_id)
            elif article_id:
                logger.info("article_id は遷移時取得値を使用: %s", article_id)
            else:
                logger.error("article_id が取得できていません")
                self._screenshot("no_article_id")
                return None

            # ── STEP 6: 「投稿する」クリック → PublishedModal（最大5回） ──
            published_url = None
            for attempt in range(1, 6):
                post_btn = self._wait_for_button("投稿する", timeout=15)
                if post_btn is None:
                    logger.error("「投稿する」ボタンなし (試行%d/5)", attempt)
                    self._screenshot(f"no_post_btn_{attempt}")
                    if attempt < 5:
                        time.sleep(3)
                    continue

                logger.info("「投稿する」クリック (試行%d/5)", attempt)
                self.driver.execute_script("arguments[0].click();", post_btn)

                # PublishedModal出現を最大20秒待機
                modal_ok = False
                for _ in range(20):
                    time.sleep(1)
                    if self._is_published_modal_visible():
                        modal_ok = True
                        break

                if modal_ok:
                    logger.info("「記事が公開されました」モーダル確認 (試行%d/5)", attempt)
                    self._screenshot(f"published_modal_{attempt}")
                    published_url = self._build_published_url(article_id)
                    break

                logger.warning("モーダルが出ませんでした (試行%d/5) URL: %s", attempt, self.driver.current_url)
                self._screenshot(f"no_modal_{attempt}")
                if attempt < 5:
                    time.sleep(3)

            if published_url is None:
                logger.error("5回リトライしてもモーダルが出ませんでした")
                return None

            # ── STEP 7: 公開URL確認（note.com か editor.note.com か） ──
            # editor.note.com は公開後も自動でnote.comに遷移しない仕様のため
            # HTTP疎通確認でnote.com上の記事が実際に公開されているか検証する
            for retry in range(1, PUBLISH_VERIFY_RETRIES + 1):
                logger.info("公開URL確認中 (%d/%d): %s", retry, PUBLISH_VERIFY_RETRIES, published_url)
                if self._verify_url_accessible(published_url):
                    logger.info("公開URL疎通OK: %s", published_url)
                    return published_url
                logger.warning("公開URLに到達できません (試行%d/%d)。%d秒後に再確認...",
                               retry, PUBLISH_VERIFY_RETRIES, retry * 5)
                time.sleep(retry * 5)

            # 最後の手段: ブラウザでnote.comユーザーページを開いて最新記事URLを取得
            logger.warning("HTTP確認が全試行で失敗。ユーザーページから記事URLを探します...")
            fallback_url = self._find_latest_article_url(article_id)
            if fallback_url:
                logger.info("フォールバックURL取得: %s", fallback_url)
                return fallback_url

            # それでも構築したURLを返す（モーダルは出ているので公開自体は成功している）
            logger.warning("疎通確認失敗だが公開自体は成功（モーダル確認済み）。構築URLを返す: %s", published_url)
            return published_url

        except Exception as e:
            logger.error("create_article 中にエラー: %s", e, exc_info=True)
            self._screenshot("create_error")
            return None

    # ─── フォールバック: ユーザーページから最新記事URL取得 ───

    def _find_latest_article_url(self, article_id: str) -> str | None:
        """note.com/{user}/ を開いて指定article_idのリンクを探す。"""
        try:
            user_page = f"https://note.com/{NOTE_USERNAME}/"
            self.driver.get(user_page)
            time.sleep(5)
            self._screenshot("user_page_fallback")

            # article_idを含むリンクを探す
            for link in self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/n/']"):
                href = link.get_attribute("href") or ""
                if article_id in href and "note.com" in href and "editor.note.com" not in href:
                    return href

            # /n/ パターンの最初のリンクを返す（最新記事が上に来る想定）
            for link in self.driver.find_elements(By.CSS_SELECTOR, f"a[href*='/{NOTE_USERNAME}/n/']"):
                href = link.get_attribute("href") or ""
                if "note.com" in href and "editor.note.com" not in href:
                    return href
        except Exception as e:
            logger.warning("フォールバックURL取得失敗: %s", e)
        return None

    # ─── ユーティリティ ───────────────────────────────────────

    def _screenshot(self, name: str) -> None:
        from config import LOG_DIR
        path = LOG_DIR / f"{name}_{int(time.time())}.png"
        try:
            self.driver.save_screenshot(str(path))
            logger.info("スクリーンショット: %s", path)
        except Exception:
            pass

    def close(self) -> None:
        self.driver.quit()
