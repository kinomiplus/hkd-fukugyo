#!/bin/bash
# ============================================================
# cronジョブセットアップスクリプト
# 実行: bash setup_cron.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Python パスを検出（仮想環境 > システム）
if [ -f "$SCRIPT_DIR/venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/venv/bin/python"
elif [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python"
else
    PYTHON="$(which python3)"
fi

LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

echo "============================================================"
echo "  北海道副業ナビ 自動投稿システム - cronセットアップ"
echo "============================================================"
echo "Pythonパス : $PYTHON"
echo "スクリプト : $SCRIPT_DIR"
echo ""
echo "追加するcronジョブ:"
echo ""
echo "  [X投稿] 毎日 7・12・17・20・22時"
echo "  0 7  * * * cd $SCRIPT_DIR && $PYTHON post_x.py >> $LOG_DIR/x_07.log 2>&1"
echo "  0 12 * * * cd $SCRIPT_DIR && $PYTHON post_x.py >> $LOG_DIR/x_12.log 2>&1"
echo "  0 17 * * * cd $SCRIPT_DIR && $PYTHON post_x.py >> $LOG_DIR/x_17.log 2>&1"
echo "  0 20 * * * cd $SCRIPT_DIR && $PYTHON post_x.py >> $LOG_DIR/x_20.log 2>&1"
echo "  0 22 * * * cd $SCRIPT_DIR && $PYTHON post_x.py >> $LOG_DIR/x_22.log 2>&1"
echo ""
echo "  [note投稿] 月・水・金 10時"
echo "  0 10 * * 1,3,5 cd $SCRIPT_DIR && $PYTHON post_note.py >> $LOG_DIR/note.log 2>&1"
echo ""
echo "  [日次レポート] 毎日 22:30"
echo "  30 22 * * * cd $SCRIPT_DIR && $PYTHON daily_report.py >> $LOG_DIR/report.log 2>&1"
echo ""
read -rp "このcronジョブを追加しますか？ [y/N]: " confirm

if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "キャンセルしました。"
    exit 0
fi

# 既存のcrontabを取得してジョブを追加
(
    crontab -l 2>/dev/null
    echo ""
    echo "# ============================================================"
    echo "# 北海道副業ナビ 自動投稿 (setup_cron.shで追加)"
    echo "# ============================================================"
    echo "0 7  * * * cd $SCRIPT_DIR && $PYTHON post_x.py >> $LOG_DIR/x_07.log 2>&1"
    echo "0 12 * * * cd $SCRIPT_DIR && $PYTHON post_x.py >> $LOG_DIR/x_12.log 2>&1"
    echo "0 17 * * * cd $SCRIPT_DIR && $PYTHON post_x.py >> $LOG_DIR/x_17.log 2>&1"
    echo "0 20 * * * cd $SCRIPT_DIR && $PYTHON post_x.py >> $LOG_DIR/x_20.log 2>&1"
    echo "0 22 * * * cd $SCRIPT_DIR && $PYTHON post_x.py >> $LOG_DIR/x_22.log 2>&1"
    echo "0 10 * * 1,3,5 cd $SCRIPT_DIR && $PYTHON post_note.py >> $LOG_DIR/note.log 2>&1"
    echo "30 22 * * * cd $SCRIPT_DIR && $PYTHON daily_report.py >> $LOG_DIR/report.log 2>&1"
) | crontab -

echo ""
echo "cronジョブを追加しました。現在のcrontab:"
echo "------------------------------------------------------------"
crontab -l
echo "------------------------------------------------------------"
echo ""
echo "確認コマンド:"
echo "  crontab -l                 # cronジョブ一覧"
echo "  tail -f $LOG_DIR/x_07.log  # X投稿ログ確認"
echo "  tail -f $LOG_DIR/note.log  # note投稿ログ確認"
echo ""
echo "テスト実行:"
echo "  cd $SCRIPT_DIR"
echo "  $PYTHON post_x.py --dry-run        # Xポスト内容確認"
echo "  $PYTHON post_note.py --dry-run     # note記事内容確認"
echo "  $PYTHON post_note.py --no-headless # ブラウザ表示でnote確認"
