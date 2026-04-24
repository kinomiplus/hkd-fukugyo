import time
import random
import logging
import json
import os
from datetime import date
from pathlib import Path

LOG_DIR = Path(__file__).parent / "logs"
DATA_DIR = Path(__file__).parent / "data"
LOG_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)


def setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")

    fh = logging.FileHandler(LOG_DIR / f"{name}_{date.today()}.log", encoding="utf-8")
    fh.setFormatter(fmt)

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def random_sleep(min_sec: float, max_sec: float) -> None:
    t = random.uniform(min_sec, max_sec)
    time.sleep(t)


def load_done_ids(kind: str) -> set:
    path = DATA_DIR / f"{kind}_{date.today()}.json"
    if path.exists():
        return set(json.loads(path.read_text()))
    return set()


def save_done_ids(kind: str, ids: set) -> None:
    path = DATA_DIR / f"{kind}_{date.today()}.json"
    path.write_text(json.dumps(list(ids), ensure_ascii=False))
