#!/bin/bash
# cronジョブのセットアップスクリプト
# 実行: bash setup_cron.sh

PYTHON=$(which python3)
DIR="$(cd "$(dirname "$0")" && pwd)"

# 既存のx_automationジョブを削除
crontab -l 2>/dev/null | grep -v "x_automation\|run_like\|run_follow\|run_reply" | crontab -

# 新しいcronジョブを追加
(crontab -l 2>/dev/null; cat <<EOF

# X自動いいね - 毎日10:00
0 10 * * * cd $DIR && $PYTHON run_like.py >> $DIR/x_automation/logs/cron_like.log 2>&1

# X自動フォロー - 毎日11:00
0 11 * * * cd $DIR && $PYTHON run_follow.py >> $DIR/x_automation/logs/cron_follow.log 2>&1

# X自動リプライ - 毎日12:00
0 12 * * * cd $DIR && $PYTHON run_reply.py >> $DIR/x_automation/logs/cron_reply.log 2>&1

EOF
) | crontab -

echo "cronジョブを設定しました:"
crontab -l | grep -A1 "X自動"
