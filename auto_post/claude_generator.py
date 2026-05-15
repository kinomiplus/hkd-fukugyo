"""Claude APIを使ってXポストとnote記事を生成する"""
import re
import json
import hashlib
import logging
import datetime
from pathlib import Path

import anthropic

from config import (
    ANTHROPIC_API_KEY,
    CONTEXT,
    X_THEMES,
    NOTE_THEMES,
    TIME_SLOTS,
    HISTORY_FILE,
    LP_URL,
    NOTE_PROFILE_URL,
)

logger = logging.getLogger(__name__)
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

BUZZ_PATTERNS_FILE = Path(__file__).parent / "buzz_patterns.json"
_LOG_DIR = Path(__file__).parent / "logs"

# ─── 時間帯別詳細ガイダンス ───────────────────────────────────────
_TIME_SLOT_DETAILS = {
    "07": {
        "persona": "通勤中・出勤前（スクロール速度が速い）",
        "length_guide": "本文80〜100文字（ハッシュタグ込み140文字以内を厳守）。一文一文を短く。",
        "style": "驚き・数字・事実でフックをかける。結論を最初に書く。テンポよく。",
        "avoid": "長い説明・複雑な構造・重い話題",
    },
    "12": {
        "persona": "ランチタイム（リラックスした気分で読む）",
        "length_guide": "本文80〜100文字（ハッシュタグ込み140文字以内を厳守）。少し余裕のある構成OK。",
        "style": "リスト形式・ステップ形式が読みやすい。有益情報・お役立ち系。",
        "avoid": "重い話・暗い内容・長すぎる説明",
    },
    "17": {
        "persona": "退勤・帰宅中（仕事への疲れや不満を感じている）",
        "length_guide": "本文80〜100文字（ハッシュタグ込み140文字以内を厳守）。感情を乗せる。",
        "style": "共感・あるある・悩み・本音系が響く。「わかる」と思わせる。",
        "avoid": "数字ばかりの無機質な投稿・ノウハウ系の説教",
    },
    "20": {
        "persona": "帰宅後（ゆっくり読める時間・情報収集意欲が高い）",
        "length_guide": "本文80〜100文字（ハッシュタグ込み140文字以内を厳守）。詳しい説明OK。",
        "style": "ハウツー・ステップ系・知識・学びになる内容。深めでためになる。",
        "avoid": "浅い内容・結論だけの投稿",
    },
    "22": {
        "persona": "就寝前（前向きな気持ちで明日に備えたい）",
        "length_guide": "本文80〜100文字（ハッシュタグ込み140文字以内を厳守）。余韻を残す締め。",
        "style": "明日への動機づけ・小さな一歩・明日試せる具体的なこと。",
        "avoid": "複雑な情報・不安を煽る内容・重い話題",
    },
}

_TREND_PRIORITY = ["副業", "転職", "北海道", "在宅", "フリーランス", "稼ぐ", "求人", "リモート", "副収入"]

_SEO_SEED_GROUPS = {
    "副業": ["北海道 副業", "札幌 副業", "北海道 在宅ワーク", "北海道 副業 初心者", "北海道 副収入"],
    "転職": ["北海道 転職", "札幌 転職", "北海道 転職エージェント", "北海道 求人", "札幌 転職 おすすめ"],
    "在宅": ["北海道 在宅ワーク", "北海道 リモートワーク", "北海道 テレワーク", "札幌 在宅 求人"],
    "フリー": ["北海道 フリーランス", "北海道 フリーランス 始め方", "札幌 フリーランス"],
    "default": ["北海道 副業", "北海道 転職", "北海道 在宅ワーク", "北海道 稼ぐ方法", "北海道 副収入"],
}

_SEO_TITLE_PATTERNS = [
    "【{year}年最新】{keyword}おすすめ{num}選｜月{amount}円稼いだ体験談",
    "{keyword}の始め方【{num}ステップ完全ガイド】北海道在住者が解説",
    "北海道で{keyword}するなら必読｜実際に月{amount}円稼げた方法{num}選",
    "{keyword}完全ガイド｜初心者が{num}ヶ月で月{amount}円達成した手順",
    "【保存版】{keyword}で稼ぐ{num}の方法｜北海道からでもできる副業",
]

_HASHTAG_MAP = {
    "副業":     ["#副業", "#副業初心者", "#副業で稼ぐ", "#副業おすすめ", "#在宅副業"],
    "転職":     ["#転職", "#転職活動", "#転職エージェント", "#転職希望", "#転職成功"],
    "北海道":   ["#北海道", "#北海道転職", "#北海道副業", "#北海道在住", "#札幌"],
    "在宅":     ["#在宅ワーク", "#リモートワーク", "#テレワーク", "#在宅勤務"],
    "稼ぐ":     ["#お金の話", "#収入アップ", "#月収公開", "#副収入"],
    "ライター": ["#Webライター", "#ライター副業", "#在宅ワーク"],
    "ポイ活":   ["#ポイ活", "#ポイント活動", "#節約"],
    "フリー":   ["#フリーランス", "#独立", "#個人事業主"],
    "会社員":   ["#会社員副業", "#サラリーマン副業", "#正社員副業"],
    "投資":     ["#投資初心者", "#少額投資", "#NISA", "#株式投資"],
    "FP":       ["#家計見直し", "#FP相談", "#家計管理"],
    "回線":     ["#光回線", "#在宅ワーク環境", "#リモートワーク"],
    "免許":     ["#運転免許", "#合宿免許", "#資格取得"],
    "社内SE":   ["#社内SE", "#エンジニア転職", "#IT転職"],
}

_THEME_TO_CATEGORY = {
    "副業": "副業",
    "転職": "転職",
    "北海道": "北海道",
    "在宅": "在宅",
    "リモート": "在宅",
    "ライター": "ライター",
    "ポイ活": "ポイ活",
    "フリーランス": "フリー",
    "会社員": "会社員",
    "稼ぐ": "稼ぐ",
    "収入": "稼ぐ",
    "投資": "投資",
    "FP": "FP",
    "家計": "FP",
    "回線": "回線",
    "免許": "免許",
    "社内SE": "社内SE",
}

# ─── ログファイルから投稿履歴を取得 ──────────────────────────────

_HOOK_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ \[INFO\] 投稿生成完了: hook=(\w+), engagement_type=(\w+)"
)
_THEME_RE = re.compile(r"\[INFO\] テーマ: (.+)")


def _get_log_history(days: int = 30) -> list[dict]:
    """auto_post/logs/x_*.log から投稿データを取得（テーマ・フック・エンゲージメントタイプ）"""
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    entries = []

    for log_file in sorted(_LOG_DIR.glob("x_*.log")):
        try:
            lines = log_file.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue

        for i, line in enumerate(lines):
            hm = _HOOK_RE.match(line)
            if not hm:
                continue
            try:
                ts = datetime.datetime.strptime(hm.group(1), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            if ts < cutoff:
                continue

            hook_id = hm.group(2)
            eng_type = hm.group(3)

            # 直後の最大6行以内でテーマを探す
            theme = ""
            for j in range(i + 1, min(i + 7, len(lines))):
                tm = _THEME_RE.search(lines[j])
                if tm:
                    theme = tm.group(1).strip()
                    break

            entries.append({
                "date": ts.isoformat(),
                "theme": theme,
                "hook_id": hook_id,
                "engagement_type": eng_type,
            })

    return sorted(entries, key=lambda e: e["date"])


# ─── SEOキーワードリサーチ ──────────────────────────────────────

def get_seo_keywords(theme: str) -> dict:
    seed_group = _SEO_SEED_GROUPS["default"]
    for key in ["副業", "転職", "在宅", "フリー"]:
        if key in theme:
            seed_group = _SEO_SEED_GROUPS[key]
            break

    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl="ja-JP", tz=540, timeout=(10, 25))
        pytrends.build_payload(seed_group[:5], cat=0, timeframe="today 3-m", geo="JP")
        interest_df = pytrends.interest_over_time()

        if not interest_df.empty:
            avg_scores = interest_df.drop(columns=["isPartial"], errors="ignore").mean()
            avg_scores = avg_scores.sort_values(ascending=False)
            ranked = [(kw, float(score)) for kw, score in avg_scores.items()]
        else:
            ranked = [(kw, 50.0) for kw in seed_group]

        primary_kw = ranked[0][0] if ranked else seed_group[0]
        pytrends.build_payload([primary_kw], cat=0, timeframe="today 3-m", geo="JP")
        related = pytrends.related_queries()

        longtail: list[str] = []
        if primary_kw in related:
            rising_df = related[primary_kw].get("rising")
            top_df = related[primary_kw].get("top")
            if rising_df is not None and not rising_df.empty:
                longtail.extend(rising_df["query"].head(3).tolist())
            if top_df is not None and not top_df.empty:
                longtail.extend(top_df["query"].head(3).tolist())

        result = {
            "primary": primary_kw,
            "longtail": longtail[:5],
            "related": [kw for kw, _ in ranked[1:4]],
            "scores": {kw: score for kw, score in ranked[:5]},
        }
        logger.info("SEOキーワード選定: primary=%s, longtail=%s", result["primary"], result["longtail"][:2])
        return result

    except ImportError:
        logger.warning("pytrends未インストール。`pip install pytrends`を実行してください。")
    except Exception as e:
        logger.warning("SEOキーワードリサーチ失敗: %s", e)

    return {
        "primary": seed_group[0],
        "longtail": [f"{seed_group[0]} 始め方", f"{seed_group[0]} おすすめ", f"{seed_group[0]} 初心者"],
        "related": seed_group[1:3],
        "scores": {},
    }


def generate_meta_description(title: str, keywords: list[str], content_preview: str) -> str:
    kw_str = "・".join(keywords[:3])
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        messages=[
            {
                "role": "user",
                "content": (
                    f"以下の情報でnote記事のメタディスクリプションを作成してください。\n\n"
                    f"タイトル: {title}\n"
                    f"キーワード: {kw_str}\n"
                    f"記事冒頭: {content_preview[:100]}\n\n"
                    "【必須ルール】\n"
                    "・120文字以内（厳守）\n"
                    "・キーワードを自然に含める\n"
                    "・クリックしたくなる文章\n"
                    "・「北海道」か「副業」か「転職」を含める\n"
                    "・メタディスクリプション本文のみ出力（説明不要）"
                ),
            }
        ],
    )
    desc = response.content[0].text.strip()
    return desc[:120] if len(desc) > 120 else desc


def analyze_competitor_structure(keyword: str) -> str:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        messages=[
            {
                "role": "user",
                "content": (
                    f"「{keyword}」というキーワードでnoteやブログの上位記事が使いがちな\n"
                    "記事構成・見出しパターンを分析してください。\n\n"
                    "【出力形式】\n"
                    "・競合が使う典型的なH2見出し（3〜5個）\n"
                    "・差別化できる独自切り口（2〜3個）\n"
                    "・このキーワードで勝てるポイント\n\n"
                    "箇条書きで簡潔に出力してください。"
                ),
            }
        ],
    )
    return response.content[0].text.strip()


# ─── Googleトレンド取得 ────────────────────────────────────

def get_google_trends() -> list[str]:
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl="ja-JP", tz=540, timeout=(10, 25))
        trending_df = pytrends.trending_searches(pn="japan")
        all_trends = trending_df[0].tolist()
        priority = [kw for kw in all_trends if any(p in kw for p in _TREND_PRIORITY)]
        others = [kw for kw in all_trends if kw not in priority]
        result = (priority + others)[:10]
        logger.info("トレンド取得成功: %s", result[:5])
        return result
    except ImportError:
        logger.warning("pytrends未インストール。`pip install pytrends` を実行してください。")
    except Exception as e:
        logger.warning("Googleトレンド取得失敗: %s", e)
    return []


def get_related_trend_keywords(trends: list[str], theme: str) -> list[str]:
    if not trends:
        return []
    related = [kw for kw in trends if any(p in kw for p in _TREND_PRIORITY)]
    theme_words = [w for w in _TREND_PRIORITY if w in theme]
    if theme_words:
        boosted = [kw for kw in related if any(w in kw for w in theme_words)]
        related = boosted + [kw for kw in related if kw not in boosted]
    return related[:3]


# ─── ハッシュタグ自動選定 ─────────────────────────────────

_FALLBACK_HASHTAGS = [
    "#副業", "#転職", "#在宅ワーク", "#北海道",
    "#副業初心者", "#転職活動", "#フリーランス",
]


def select_hashtags(content: str, theme: str, trends: list[str], count: int = 3) -> list[str]:
    selected: list[str] = []

    if trends:
        for kw in trends[:15]:
            for priority_kw in _TREND_PRIORITY:
                if priority_kw in kw:
                    tag = f"#{priority_kw}"
                    if tag not in selected:
                        selected.append(tag)
                    break
            if len(selected) >= count:
                break

    if len(selected) < count:
        now = datetime.datetime.now()
        offset = (now.timetuple().tm_yday + now.hour) % len(_FALLBACK_HASHTAGS)
        rotated = _FALLBACK_HASHTAGS[offset:] + _FALLBACK_HASHTAGS[:offset]
        for tag in rotated:
            if tag not in selected:
                selected.append(tag)
            if len(selected) >= count:
                break

    return selected[:count]


def trim_to_fit(content: str, hashtags: list[str], limit: int = 140) -> tuple[str, list[str]]:
    """本文とハッシュタグを合わせて limit 文字以内に収める。
    1. ハッシュタグを段階的に削減
    2. それでも超える場合は本文を文末記号で自然に切る（URL途中では切らない）
    """
    if len(f"{content}\n{' '.join(hashtags)}") <= limit:
        return content, hashtags

    # ハッシュタグを段階的に削減
    for n in range(len(hashtags) - 1, 0, -1):
        reduced = hashtags[:n]
        if len(f"{content}\n{' '.join(reduced)}") <= limit:
            logger.info("ハッシュタグ%d個に削減して%d文字に収めた", n, len(f"{content}\n{' '.join(reduced)}"))
            return content, reduced

    # タグ1個でも超える場合は本文を削る
    single_tag = hashtags[:1]
    max_body = limit - len(f"\n{' '.join(single_tag)}")

    if len(content) > max_body:
        trimmed = content[:max_body]

        # URLが途中で切れていないか確認（切れていたらURL前まで後退）
        url_match = re.search(r"https?://\S*$", trimmed)
        if url_match and url_match.start() >= int(max_body * 0.4):
            trimmed = trimmed[:url_match.start()].rstrip(" 　→")
        else:
            # 末尾の自然な区切りで切る（70%以上残っていれば採用）
            for punct in ["。", "！", "？", "✅", "🙌", "\n"]:
                pos = trimmed.rfind(punct)
                if pos >= int(max_body * 0.7):
                    trimmed = trimmed[:pos + 1]
                    break

        logger.info("本文トリム: %d→%d文字", len(content), len(trimmed))
        content = trimmed

    return content, single_tag


def append_hashtags(content: str, hashtags: list[str], total_limit: int = 140) -> str:
    """本文末尾にハッシュタグを追記。必ず total_limit 文字以内に収める。"""
    content, adjusted_tags = trim_to_fit(content, hashtags, total_limit)
    return f"{content}\n{' '.join(adjusted_tags)}"


# ─── バズパターン ──────────────────────────────────────

def load_buzz_patterns() -> dict:
    if BUZZ_PATTERNS_FILE.exists():
        return json.loads(BUZZ_PATTERNS_FILE.read_text(encoding="utf-8"))
    return {"patterns": [], "hooks": [], "buzz_keywords": []}


def build_buzz_context(theme: str, engagement_type: str = "informational") -> str:
    data = load_buzz_patterns()
    patterns = data.get("patterns", [])
    buzz_keywords = data.get("buzz_keywords", [])

    def relevance(p: dict) -> int:
        score = 0
        if p.get("engagement") == "very_high":
            score += 2
        elif p.get("engagement") == "high":
            score += 1
        if any(tag in theme for tag in p.get("tags", [])):
            score += 3
        if p.get("engagement_type") == engagement_type:
            score += 4
        return score

    top_patterns = sorted(patterns, key=relevance, reverse=True)[:3]

    lines = ["【バズりやすい投稿パターン（参考にする）】"]
    for p in top_patterns:
        lines.append(f"▼{p['name']}: {p['example'][:80]}")

    lines.append("\n【バズるキーワード（積極的に使う）】")
    lines.append("・" + "　・".join(buzz_keywords[:6]))

    return "\n".join(lines)


def select_hook(history: dict) -> dict:
    """直近3日間で使ったフックを除外し、30日間で最も使用頻度が低いフックを選ぶ。"""
    data = load_buzz_patterns()
    hooks = data.get("hooks", [])
    if not hooks:
        return {"id": "honest", "text": "正直に言う。", "style": "本音系"}

    now = datetime.datetime.now()
    cutoff_3d = now - datetime.timedelta(days=3)
    cutoff_30d = now - datetime.timedelta(days=30)

    log_entries = _get_log_history(days=30)

    # 直近3日に使ったフック（使用禁止）
    recent_3d_hooks: set[str] = set()
    for e in log_entries:
        try:
            if e["hook_id"] and datetime.datetime.fromisoformat(e["date"]) > cutoff_3d:
                recent_3d_hooks.add(e["hook_id"])
        except (ValueError, KeyError):
            pass
    for p in history.get("x_posts", []):
        try:
            if datetime.datetime.fromisoformat(p["date"]) > cutoff_3d and p.get("hook_id"):
                recent_3d_hooks.add(p["hook_id"])
        except (ValueError, KeyError):
            pass

    # 直近30日の使用回数
    counts: dict[str, int] = {}
    for e in log_entries:
        try:
            if e["hook_id"] and datetime.datetime.fromisoformat(e["date"]) > cutoff_30d:
                counts[e["hook_id"]] = counts.get(e["hook_id"], 0) + 1
        except (ValueError, KeyError):
            pass
    for p in history.get("x_posts", []):
        try:
            if datetime.datetime.fromisoformat(p["date"]) > cutoff_30d and p.get("hook_id"):
                counts[p["hook_id"]] = counts.get(p["hook_id"], 0) + 1
        except (ValueError, KeyError):
            pass

    # 3日以内に使ったフックを除外
    candidates = [h for h in hooks if h["id"] not in recent_3d_hooks]
    if not candidates:
        candidates = hooks  # 全部使い切っていたらリセット

    # 使用回数が最少のものを優先
    min_count = min(counts.get(h["id"], 0) for h in candidates)
    least_used = [h for h in candidates if counts.get(h["id"], 0) == min_count]

    # 最後に使ったhookとは被らせない
    last_hook_ids = [e["hook_id"] for e in log_entries if e["hook_id"]]
    last_hook_id = last_hook_ids[-1] if last_hook_ids else ""
    non_repeat = [h for h in least_used if h["id"] != last_hook_id]

    chosen = (non_repeat or least_used)[0]
    logger.info("フック選定: %s（3日除外: %s）", chosen["id"], list(recent_3d_hooks))
    return chosen


# ─── 履歴管理 ────────────────────────────────────────────────

def load_history() -> dict:
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    return {"x_posts": [], "note_articles": []}


def save_history(history: dict) -> None:
    HISTORY_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_recent_x_themes(history: dict, days: int = 14) -> list[str]:
    """post_history.json とログファイルの両方から直近N日のテーマを取得。"""
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)

    # post_history.json から
    history_themes = [
        p["theme"]
        for p in history.get("x_posts", [])
        if datetime.datetime.fromisoformat(p["date"]) > cutoff
    ]

    # ログファイルから（履歴が空の場合も有効）
    log_entries = _get_log_history(days=days)
    log_themes = [e["theme"] for e in log_entries if e["theme"]]

    # 順序を保ちつつ重複除去
    seen: set[str] = set()
    all_themes: list[str] = []
    for t in history_themes + log_themes:
        if t not in seen:
            seen.add(t)
            all_themes.append(t)

    logger.info("直近%d日の使用テーマ: %d種（history=%d, log=%d）",
                days, len(all_themes), len(history_themes), len(log_themes))
    return all_themes


def get_recent_note_titles(history: dict) -> list[str]:
    return [a["title"] for a in history.get("note_articles", [])[-10:]]


def get_weekly_engagement_stats(history: dict) -> dict:
    now = datetime.datetime.now()
    week_start = now - datetime.timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

    stats: dict[str, int] = {
        "reply_prompt": 0, "quotable": 0, "informational": 0,
        "lp_cta": 0, "note_cta": 0,
    }
    for p in history.get("x_posts", []):
        try:
            post_date = datetime.datetime.fromisoformat(p["date"])
            if post_date >= week_start:
                etype = p.get("engagement_type", "informational")
                stats[etype] = stats.get(etype, 0) + 1
        except (ValueError, KeyError):
            pass
    return stats


def decide_engagement_type(history: dict) -> str:
    """今週の投稿バランスを見て次のエンゲージメントタイプを決定。
    週間目標: lp_cta 1〜2本 / note_cta 1本 / reply_prompt 2〜3本 / quotable 1〜2本
    """
    stats = get_weekly_engagement_stats(history)

    # ログからも今週の統計を補完
    log_entries = _get_log_history(days=7)
    now = datetime.datetime.now()
    week_start = (now - datetime.timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    for e in log_entries:
        try:
            if datetime.datetime.fromisoformat(e["date"]) >= week_start and e.get("engagement_type"):
                et = e["engagement_type"]
                stats[et] = stats.get(et, 0) + 1
        except (ValueError, KeyError):
            pass

    logger.info("今週のエンゲージメント統計: %s", stats)

    # 優先度順に決定（LP・note誘導を週2〜3本確保）
    if stats.get("lp_cta", 0) < 1:
        return "lp_cta"
    if stats.get("reply_prompt", 0) < 2:
        return "reply_prompt"
    if stats.get("note_cta", 0) < 1:
        return "note_cta"
    if stats.get("quotable", 0) < 1:
        return "quotable"
    if stats.get("lp_cta", 0) < 2:
        return "lp_cta"
    return "informational"


def record_x_post(
    history: dict,
    theme: str,
    content: str,
    tweet_id: str = "",
    hook_id: str = "",
    engagement_type: str = "informational",
) -> None:
    history.setdefault("x_posts", []).append({
        "date": datetime.datetime.now().isoformat(),
        "theme": theme,
        "content": content,
        "tweet_id": tweet_id,
        "hook_id": hook_id,
        "engagement_type": engagement_type,
    })
    history["x_posts"] = history["x_posts"][-200:]
    save_history(history)


def record_note_article(history: dict, title: str, url: str = "") -> None:
    history.setdefault("note_articles", []).append({
        "date": datetime.datetime.now().isoformat(),
        "title": title,
        "url": url,
    })
    save_history(history)


# ─── コンテンツ生成 ───────────────────────────────────────────

def generate_x_post(time_hour: str) -> dict:
    """指定時間帯のX投稿を1本生成して返す。文字数は必ず140文字以内。"""
    history = load_history()

    # ① 直近14日のテーマ（ログ+履歴）を除外
    recent_themes = get_recent_x_themes(history, days=14)
    available = [t for t in X_THEMES if t not in recent_themes]
    if not available:
        logger.info("全テーマを14日以内に使用済。リセット。")
        available = X_THEMES[:]

    # ② 日時ベースのシードでテーマリストをローテーション（同じ日時は同じ順序を保証）
    today_key = datetime.datetime.now().strftime("%Y%m%d") + time_hour
    seed = int(hashlib.md5(today_key.encode()).hexdigest()[:8], 16)
    offset = seed % len(available)
    rotated = available[offset:] + available[:offset]
    available_for_prompt = rotated[:10]  # 10テーマを提示（6→10に拡大）
    default_theme = available_for_prompt[0]

    # ③ トレンド取得
    trends = get_google_trends()
    trend_keywords = get_related_trend_keywords(trends, default_theme)

    # ④ エンゲージメントタイプ・フック決定
    engagement_type = decide_engagement_type(history)
    hook = select_hook(history)

    time_desc = TIME_SLOTS.get(time_hour, "")
    slot_detail = _TIME_SLOT_DETAILS.get(time_hour, {})
    available_str = "\n".join(f"・{t}" for t in available_for_prompt)
    recent_str = ("・" + "\n・".join(recent_themes[:10])) if recent_themes else "なし"
    trend_str = "・" + "\n・".join(trend_keywords) if trend_keywords else "なし"

    # ⑤ エンゲージメントタイプ別の追加指示
    engagement_guide = {
        "reply_prompt": (
            "【今回の投稿タイプ：返信促進型】\n"
            "・必ず読者に問いかける一文で締める（例：「あなたはどうですか？」「コメントで教えてほしい」）\n"
            "・ぼく自身の体験談や答えを先に書き、読者の返信を自然に促す"
        ),
        "quotable": (
            "【今回の投稿タイプ：引用RT型】\n"
            "・引用RTされやすい「格言・断言・名言」形式で書く\n"
            "・「〇〇は〇〇だ」という強い断言を1文目に入れる\n"
            "・シンプルで覚えやすい言葉を選ぶ"
        ),
        "informational": (
            "【今回の投稿タイプ：有益情報型】\n"
            "・数字・事実・具体例で読者の学びになる内容にする\n"
            "・北海道特化の情報を積極的に盛り込む"
        ),
        "lp_cta": (
            "【今回の投稿タイプ：LP誘導型】\n"
            f"・URLが「{LP_URL}」（32文字）入るため、本文は【最大65文字】で生成すること\n"
            "・副業や転職に関心を持った読者をLPへ自然に誘導する\n"
            "・体験談（数字入り）を書き、最後にLPのURLを全文で記載する\n"
            f"・最終行に必ず「詳しくはこちら → {LP_URL}」を入れる\n"
            "・宣伝感を出さず「まとめた」「公開中」など柔らかく表現する"
        ),
        "note_cta": (
            "【今回の投稿タイプ：note誘導型】\n"
            f"・URLが「{NOTE_PROFILE_URL}」（約30文字）入るため、本文は【最大65文字】で生成すること\n"
            "・副業や転職の具体的な情報に関心を持った読者をnoteへ誘導する\n"
            "・teaser型：興味を持たせて「続きはnote」と引っ張る\n"
            f"・最終行に必ず「続きはnoteで → {NOTE_PROFILE_URL}」を入れる\n"
            "・宣伝感を出さず体験談→note誘導の自然な流れで書く"
        ),
    }.get(engagement_type, "")

    # ⑥ バズパターン取得
    buzz_context = build_buzz_context(default_theme, engagement_type)

    # ⑦ 時間帯詳細ガイダンス
    time_guide = (
        f"【{time_hour}時の読者プロフィール】{slot_detail.get('persona', time_desc)}\n"
        f"【文字数の目安】{slot_detail.get('length_guide', '80〜100文字')}\n"
        f"【文体・スタイル】{slot_detail.get('style', '')}\n"
        f"【避けること】{slot_detail.get('avoid', '')}"
    )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        system=[
            {
                "type": "text",
                "text": CONTEXT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": (
                    f"今から{time_hour}時向けのX投稿を1本作成してください。\n\n"
                    f"【最近使ったテーマ（絶対に重複禁止）】\n{recent_str}\n\n"
                    f"【使えるテーマ候補（この中から1つ選ぶ）】\n{available_str}\n\n"
                    f"【今日のトレンドキーワード（自然に盛り込む）】\n{trend_str}\n\n"
                    f"{time_guide}\n\n"
                    f"{engagement_guide}\n\n"
                    f"【今回のフック（最初の一文に使う）】\n「{hook['text']}」（{hook['style']}）\n\n"
                    f"{buzz_context}\n\n"
                    "【必須ルール（絶対に守ること）】\n"
                    "・本文は【最大100文字】で生成する\n"
                    "  ※ ハッシュタグが別途30〜40文字追加される。本文100文字以下にしないと140文字を超える\n"
                    "  ※ 文字数は必ず自分でカウントして確認してから出力すること\n"
                    "・文章は必ず完結した形で終わる。「…」で切らない\n"
                    "・数字・具体例を必ず含める\n"
                    "・北海道特化ネタを優先\n"
                    "・絵文字は1〜2個まで\n"
                    "・宣伝臭は出さない\n"
                    "・バズパターンを1つ参考にして書く\n"
                    "・フックの文から始める（そのままでもアレンジしてもOK）\n\n"
                    "【人間らしさのルール（最重要）】\n"
                    "・AI感・教科書感を絶対に出さない\n"
                    "・完璧な文章より友人へのLINEみたいな自然さを優先\n"
                    "・失敗談・本音・迷い・愚痴を積極的に入れる\n"
                    "・北海道在住だからこそわかるというフレーズは使わない\n"
                    "・だべは多用しない（1投稿に1回まで）\n"
                    "・毎回同じような締め方をしない\n"
                    "・たまに弱音・不安・葛藤を見せる\n\n"
                    "以下の形式のみで出力（余計な説明不要）:\n"
                    "THEME: 選んだテーマ\n"
                    "POST: 投稿本文（100文字以内・ハッシュタグなし）"
                ),
            }
        ],
    )

    text = response.content[0].text.strip()
    logger.debug("Claude応答 (X):\n%s", text)

    theme_match = re.search(r"^THEME:\s*(.+)", text, re.MULTILINE)
    post_match = re.search(r"^POST:\s*(.+)", text, re.MULTILINE | re.DOTALL)

    theme = theme_match.group(1).strip() if theme_match else default_theme
    content = post_match.group(1).strip() if post_match else text.split("\n")[-1]

    # ⑧ ハッシュタグ選定・追記（trim_to_fit で必ず140字以内に収める）
    hashtags = select_hashtags(content, theme, trends)
    full_post = append_hashtags(content, hashtags)

    logger.info(
        "投稿生成完了: hook=%s, engagement_type=%s, time=%s",
        hook["id"],
        engagement_type,
        time_hour,
    )

    return {
        "theme": theme,
        "content": content,
        "hashtags": hashtags,
        "full_post": full_post,
        "hook_id": hook["id"],
        "engagement_type": engagement_type,
    }


def generate_note_article() -> dict:
    """note記事を1本生成して返す。"""
    history = load_history()
    recent_titles = get_recent_note_titles(history)

    available = [t for t in NOTE_THEMES if t not in recent_titles]
    if not available:
        available = NOTE_THEMES[:]

    theme = available[0]
    recent_str = ("・" + "\n・".join(recent_titles)) if recent_titles else "なし"
    current_year = datetime.datetime.now().year

    seo = get_seo_keywords(theme)
    primary_kw = seo["primary"]
    longtail_kws = seo["longtail"]
    all_seo_kws = [primary_kw] + longtail_kws[:3]
    seo_kw_str = "・" + "\n・".join(all_seo_kws)

    trends = get_google_trends()
    trend_keywords = get_related_trend_keywords(trends, theme)
    trend_str = "・" + "\n・".join(trend_keywords) if trend_keywords else "なし"

    competitor_analysis = analyze_competitor_structure(primary_kw)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=7000,
        system=[
            {
                "type": "text",
                "text": CONTEXT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": (
                    f"以下のテーマでSEO最適化されたnote記事を1本作成してください。\n\n"
                    f"【記事テーマ】\n{theme}\n\n"
                    f"【最近書いた記事（重複禁止）】\n{recent_str}\n\n"
                    f"【メインSEOキーワード（タイトル・導入・まとめに必ず入れる）】\n{seo_kw_str}\n\n"
                    f"【今日のトレンドキーワード（記事内に自然に組み込む）】\n{trend_str}\n\n"
                    f"【競合分析（差別化のヒント）】\n{competitor_analysis}\n\n"
                    "【必須ルール】\n"
                    "・3,500〜4,500文字（厳守。文字数が足りなければ各セクションを詳しく書く）\n"
                    f"・タイトルにメインキーワード「{primary_kw}」を必ず含める\n"
                    "・タイトルに数字を入れる（例：5選・3ステップ・完全ガイド）\n"
                    f"・タイトルに【{current_year}年最新】や【保存版】などを入れてCTRを高める\n"
                    "・構成：導入（300字）→H2×4〜5本（各600〜800字）→まとめ（300字）→LP誘導\n"
                    "・H2見出しを4〜5個、各H2の下にH3見出しを2〜3個配置する\n"
                    "・導入文の最初の100字以内にメインキーワードを自然に入れる\n"
                    "・まとめセクションにもメインキーワードを再度入れる\n"
                    "・数字・具体例必須（金額・期間・割合・求人数など）\n"
                    "・北海道特化の情報を積極的に盛り込む（地名・気候・求人状況・平均年収など）\n"
                    f"・LP誘導リンクを本文中3箇所に挿入（導入後・本文中盤・まとめ前）:\n"
                    f"  「▶ 詳しくはこちら → {LP_URL}」\n"
                    "・宣伝臭は出さず、体験談ベースで語る\n"
                    "・ロングテールキーワードを見出しや本文に自然に散りばめる\n\n"
                    "以下の形式のみで出力（余計な説明不要）:\n"
                    "TITLE: 記事タイトル\n"
                    "---\n"
                    "記事本文（Markdown形式）"
                ),
            }
        ],
    )

    text = response.content[0].text.strip()
    logger.debug("Claude応答 (note): %d文字", len(text))

    title_match = re.search(r"^TITLE:\s*(.+)", text, re.MULTILINE)
    sep_index = text.find("---")

    title = title_match.group(1).strip() if title_match else theme
    content = text[sep_index + 3:].strip() if sep_index != -1 else text

    meta_desc = generate_meta_description(title, all_seo_kws, content[:200])

    logger.info("SEOキーワード(primary): %s", primary_kw)
    logger.info("ロングテール: %s", longtail_kws[:3])
    logger.info("メタディスクリプション(%d字): %s", len(meta_desc), meta_desc)

    return {
        "title": title,
        "content": content,
        "meta_description": meta_desc,
        "seo_keywords": seo,
    }
