"""Google Sheetsへの投稿ログ記録

スプレッドシートの列構成:
  A列: 投稿時間
  B列: 投稿文
  C列: 文字数
  D列: 投稿済みチェックボックス
  E列: 投稿日付
"""
import datetime
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_client():
    import gspread
    from google.oauth2.service_account import Credentials
    from config import GOOGLE_CREDENTIALS_FILE

    creds_path = Path(GOOGLE_CREDENTIALS_FILE)
    if not creds_path.exists():
        raise FileNotFoundError(
            f"Google認証ファイルが見つかりません: {creds_path}\n"
            "サービスアカウントのJSONキーを配置してください。"
        )

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(str(creds_path), scopes=scopes)
    return gspread.authorize(creds)


def _apply_checkbox(sheet, row_index: int) -> None:
    """指定行のD列（4列目）をチェックボックス形式に設定する"""
    requests = [{
        "setDataValidation": {
            "range": {
                "sheetId": sheet.id,
                "startRowIndex": row_index - 1,
                "endRowIndex": row_index,
                "startColumnIndex": 3,  # D列 (0-indexed)
                "endColumnIndex": 4,
            },
            "rule": {
                "condition": {"type": "BOOLEAN"},
                "showCustomUi": True,
            },
        }
    }]
    sheet.spreadsheet.batch_update({"requests": requests})


def append_x_post(content: str, post_time: str, posted: bool = False) -> bool:
    """X投稿内容をスプレッドシートに追記する。

    Args:
        content:   投稿文
        post_time: 投稿時間帯（例: "07"）
        posted:    実際に投稿済みなら True（dry-run時は False）

    Returns:
        書き込み成功なら True
    """
    from config import SPREADSHEET_ID, SHEET_NAME

    if not SPREADSHEET_ID:
        logger.warning(
            "SPREADSHEET_IDが未設定のためスプレッドシートへの書き込みをスキップします。"
        )
        return False

    try:
        client = _get_client()
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)

        now = datetime.datetime.now()
        time_str = now.strftime("%H:%M")
        date_str = now.strftime("%Y-%m-%d")

        row = [
            time_str,                    # A列: 投稿時間
            content,                     # B列: 投稿文
            len(content),                # C列: 文字数
            "TRUE" if posted else "FALSE",  # D列: 投稿済み（チェックボックス用）
            date_str,                    # E列: 投稿日付
        ]
        sheet.append_row(row, value_input_option="USER_ENTERED")

        # 追記した行のD列をチェックボックス形式に設定
        row_index = len(sheet.get_all_values())
        _apply_checkbox(sheet, row_index)

        logger.info(
            "スプレッドシートへの書き込み完了 | 行: %d | 投稿済み: %s",
            row_index,
            posted,
        )
        return True

    except FileNotFoundError as e:
        logger.error("認証ファイルエラー: %s", e)
        return False
    except Exception as e:
        logger.error("スプレッドシートへの書き込み失敗: %s", e)
        return False
