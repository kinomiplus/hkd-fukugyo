#!/usr/bin/env python3
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

sys.path.insert(0, str(Path(__file__).parent))

from x_automation.browser import create_driver
from x_automation.auth import login
from x_automation.reply_bot import run as run_replies

USERNAME = os.environ["X_USERNAME"]
PASSWORD = os.environ["X_PASSWORD"]
EMAIL = os.environ.get("X_EMAIL", "")
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
DAILY_LIMIT = int(os.environ.get("REPLY_DAILY_LIMIT", "10"))
HEADLESS = os.environ.get("HEADLESS", "true").lower() == "true"

if __name__ == "__main__":
    driver = create_driver(headless=HEADLESS)
    try:
        if not login(driver, USERNAME, PASSWORD, EMAIL):
            sys.exit(1)
        run_replies(driver, api_key=ANTHROPIC_API_KEY, daily_limit=DAILY_LIMIT)
    finally:
        driver.quit()
