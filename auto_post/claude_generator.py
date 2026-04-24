"""Claude APIを使ってXポストとnote記事を生成する"""
import re
import json
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
)

logger = logging.getLogger(__name__)
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

BUZZ_PATTERNS_FILE = Path(__file__).parent / "buzz_patterns.json"

# ─── 時間帯別詳細ガイダンス ───────────────────────────────────────
_TIME_SLOT_DETAILS = {
    "07": {
        "persona": "通勤中・出勤前（スクロール速度が速い）",
        "length_guide": "本文100〜110文字（ハッシュタグ含む全体で140文字以内）。一文一文を短く。",
        "style": "驚き・数字・事実でフックをかける。結論を最初に書く。テンポよく。",
        "avoid": "長い説明・複雑な構造・重い話題",
    },
    "12": {
        "persona": "ランチタイム（リラックスした気分で読む）",
        "length_guide": "本文100〜110文字（ハッシュタグ含む全体で140文字以内）。少し余裕のある構成OK。",
        "style": "リスト形式・ステップ形式が読みやすい。有益情報・お役立ち系。",
        "avoid": "重い話・暗い内容・長すぎる説明",
    },
    "17": {
        "persona": "退勤・帰宅中（仕事への疲れや不満を感じている）",
        "length_guide": "本文100〜110文字（ハッシュタグ含む全体で140文字以内）。感情を乗せる。",
        "style": "共感・あるある・悩み・本音系が響く。「わかる」と思わせる。",
        "avoid": "数字ばかりの無機質な投稿・ノウハウ系の説教",
    },
    "20": {
        "persona": "帰宅後（ゆっくり読める時間・情報収集意欲が高い）",
        "length_guide": "本文100〜110文字（ハッシュタグ含む全体で140文字以内）。詳しい説明OK。",
        "style": "ハウツー・ステップ系・知識・学びになる内容。深めでためになる。",
        "avoid": "浅い内容・結論だけの投稿",
    },
    "22": {
        "persona": "就寝前（前向きな気持ちで明日に備えたい）",
        "length_guide": "本文100〜110文字（ハッシュタグ含む全体で140文字以内）。余韻を残す締め。",
        "style": "明日への動機づけ・小さな一歩・明日試せる具体的なこと。",
        "avoid": "複雑な情報・不安を煽る内容・重い話題",
    },
}

# ① Googleトレンド用 優先マッチキーワード
_TREND_PRIORITY = ["副業", "転職", "北海道", "在宅", "フリーランス", "稼ぐ", "求人", "リモート", "副収入"]

# ─── SEOキーワードリサーチ設定 ──────────────────────────────────

# pytrends用シードキーワードグループ（5個以内／グループ）
_SEO_SEED_GROUPS = {
    "副業": ["北海道 副業", "札幌 副業", "北海道 在宅ワーク", "北海道 副業 初心者", "北海道 副収入"],
    "転職": ["北海道 転職", "札幌 転職", "北海道 転職エージェント", "北海道 求人", "札幌 転職 おすすめ"],
    "在宅": ["北海道 在宅ワーク", "北海道 リモートワーク", "北海道 テレワーク", "札幌 在宅 求人"],
    "フリー": ["北海道 フリーランス", "北海道 フリーランス 始め方", "札幌 フリーランス"],
    "default": ["北海道 副業", "北海道 転職", "北海道 在宅ワーク", "北海道 稼ぐ方法", "北海道 副収入"],
}

# CTR最適化タイトルパターン
_SEO_TITLE_PATTERNS = [
    "【{year}年最新】{keyword}おすすめ{num}選｜月{amount}円稼いだ体験談",
    "{keyword}の始め方【{num}ステップ完全ガイド】北海道在住者が解説",
    "北海道で{keyword}するなら必読｜実際に月{amount}円稼げた方法{num}選",
    "{keyword}完全ガイド｜初心者が{num}ヶ月で月{amount}円達成した手順",
    "【保存版】{keyword}で稼ぐ{num}の方法｜北海道からでもできる副業",
]

# ② ハッシュタグマスター（テーマ→候補リスト）
_HASHTAG_MAP = {
    "副業":     ["#副業", "#副業初心者", "#副業で稼ぐ", "#副業おすすめ", "#在宅副業"],
    "転職":     ["#転職", "#転職活動", "#転職エージェント", "#転職希望", "#転職成功"],
    "北海道":   ["#北海道", "#北海道転職", "#北海道副業", "#北海道在住", "#札幌"],
    "在宅":     ["#在宅ワーク", "#リモートワーク", "#テレワーク", "#在宅勤務"],
    "稼ぐ":     ["#お金の話", "#収入アップ", "#月収公開", "#副収入"],
    "ライター": ["#Webライター", "#ライター副業", "#クラウドワークス"],
    "ポイ活":   ["#ポイ活", "#ポイント活動", "#節約"],
    "フリー":   ["#フリーランス", "#独立", "#個人事業主"],
    "会社員":   ["#会社員副業", "#サラリーマン副業", "#正社員副業"],
}

# テーマ文字列 → 関連カテゴリのマッピング
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
}


# ─── SEOキーワードリサーチ ──────────────────────────────────────

def get_seo_keywords(theme: str) -> dict:
    """pytrendsでSEOキーワードリサーチを行い、ロングテールキーワードを返す。
    Returns: {"primary": str, "longtail": [str], "related": [str], "scores": dict}
    """
    # テーマに合ったシードグループを選択
    seed_group = _SEO_SEED_GROUPS["default"]
    for key in ["副業", "転職", "在宅", "フリー"]:
        if key in theme:
            seed_group = _SEO_SEED_GROUPS[key]
            break

    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl="ja-JP", tz=540, timeout=(10, 25))

        # 検索ボリューム比較（interest_over_time）
        pytrends.build_payload(seed_group[:5], cat=0, timeframe="today 3-m", geo="JP")
        interest_df = pytrends.interest_over_time()

        if not interest_df.empty:
            avg_scores = interest_df.drop(columns=["isPartial"], errors="ignore").mean()
            avg_scores = avg_scores.sort_values(ascending=False)
            ranked = [(kw, float(score)) for kw, score in avg_scores.items()]
        else:
            ranked = [(kw, 50.0) for kw in seed_group]

        # 上位キーワードの関連クエリ（ロングテール）を取得
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

    # フォールバック：シードグループをそのまま使用
    return {
        "primary": seed_group[0],
        "longtail": [
            f"{seed_group[0]} 始め方",
            f"{seed_group[0]} おすすめ",
            f"{seed_group[0]} 初心者",
        ],
        "related": seed_group[1:3],
        "scores": {},
    }


def generate_meta_description(title: str, keywords: list[str], content_preview: str) -> str:
    """SEO最適化メタディスクリプションを生成する（120文字以内）。"""
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
    """指定キーワードで上位表示される記事の構成をClaude分析で返す。"""
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


# ─── ① Googleトレンド取得 ────────────────────────────────────

def get_google_trends() -> list[str]:
    """日本のGoogleトレンドから副業・転職・北海道関連キーワードを取得する。
    失敗時は空リストを返す。"""
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
    """トレンドリストからテーマに関連するキーワードだけ返す（最大3件）。"""
    if not trends:
        return []
    related = [kw for kw in trends if any(p in kw for p in _TREND_PRIORITY)]
    theme_words = [w for w in _TREND_PRIORITY if w in theme]
    if theme_words:
        boosted = [kw for kw in related if any(w in kw for w in theme_words)]
        related = boosted + [kw for kw in related if kw not in boosted]
    return related[:3]


# ─── ② ハッシュタグ自動選定 ─────────────────────────────────

# トレンド失敗時のフォールバックリスト（検索ボリューム優先順）
_FALLBACK_HASHTAGS = [
    "#副業", "#転職", "#在宅ワーク", "#北海道",
    "#副業初心者", "#転職活動", "#フリーランス",
]


def select_hashtags(content: str, theme: str, trends: list[str], count: int = 3) -> list[str]:
    """投稿内容・テーマ・トレンドからハッシュタグを最大3個選定して返す。
    トレンド取得成功時は上位キーワードを使用。失敗時はローテーションで選定。
    """
    selected: list[str] = []

    if trends:
        # トレンド成功時：_TREND_PRIORITY に一致するキーワードをハッシュタグ化
        for kw in trends[:15]:
            for priority_kw in _TREND_PRIORITY:
                if priority_kw in kw:
                    tag = f"#{priority_kw}"
                    if tag not in selected:
                        selected.append(tag)
                    break
            if len(selected) >= count:
                break

    # 不足分を日時ベースのローテーションで補充
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


def append_hashtags(content: str, hashtags: list[str], total_limit: int = 140) -> str:
    """本文末尾にハッシュタグを追記する。"""
    tag_str = " ".join(hashtags)
    combined = f"{content}\n{tag_str}"
    if len(combined) > total_limit:
        logger.warning("投稿文字数が%d文字を超えています（%d文字）", total_limit, len(combined))
    return combined


# ─── ③ 競合投稿パターン ──────────────────────────────────────

def load_buzz_patterns() -> dict:
    """buzz_patterns.jsonを読み込む。"""
    if BUZZ_PATTERNS_FILE.exists():
        return json.loads(BUZZ_PATTERNS_FILE.read_text(encoding="utf-8"))
    return {"patterns": [], "buzz_keywords": []}


def build_buzz_context(theme: str, engagement_type: str = "informational") -> str:
    """テーマ・エンゲージメントタイプに合うバズパターンとキーワードをプロンプト用文字列に整形する。"""
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
        # エンゲージメントタイプが一致する場合は優先
        if p.get("engagement_type") == engagement_type:
            score += 4
        return score

    top_patterns = sorted(patterns, key=relevance, reverse=True)[:3]

    lines = ["【バズりやすい投稿パターン（参考にする）】"]
    for p in top_patterns:
        lines.append(f"▼{p['name']}: {p['example']}")

    lines.append("\n【バズるキーワード（積極的に使う）】")
    lines.append("・" + "　・".join(buzz_keywords[:6]))

    return "\n".join(lines)


def select_hook(history: dict) -> dict:
    """直近で使っていないフックを選んで返す。"""
    data = load_buzz_patterns()
    hooks = data.get("hooks", [])
    if not hooks:
        return {"id": "honest", "text": "正直に言う。", "style": "本音系"}

    # 直近30日に使ったhook_idを取得
    cutoff = datetime.datetime.now() - datetime.timedelta(days=30)
    recent_hook_ids = [
        p.get("hook_id", "")
        for p in history.get("x_posts", [])
        if datetime.datetime.fromisoformat(p["date"]) > cutoff and p.get("hook_id")
    ]

    # 使用回数でランク付けし、最も少ないものを選ぶ
    counts = {h["id"]: recent_hook_ids.count(h["id"]) for h in hooks}
    min_count = min(counts.values(), default=0)
    candidates = [h for h in hooks if counts[h["id"]] == min_count]

    # 最後に使ったhook_idと被らないようにする
    last_hook_id = recent_hook_ids[-1] if recent_hook_ids else ""
    non_repeat = [h for h in candidates if h["id"] != last_hook_id]
    return (non_repeat or candidates)[0]


def get_weekly_engagement_stats(history: dict) -> dict:
    """今週（月曜から）のエンゲージメントタイプ別投稿数を返す。"""
    now = datetime.datetime.now()
    week_start = now - datetime.timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

    stats = {"reply_prompt": 0, "quotable": 0, "informational": 0}
    for p in history.get("x_posts", []):
        post_date = datetime.datetime.fromisoformat(p["date"])
        if post_date >= week_start:
            etype = p.get("engagement_type", "informational")
            stats[etype] = stats.get(etype, 0) + 1
    return stats


def decide_engagement_type(history: dict) -> str:
    """今週の投稿バランスを見て、次の投稿のエンゲージメントタイプを決定する。
    - reply_prompt: 週2〜3本を目標
    - quotable: 週1〜2本を目標
    - informational: それ以外
    """
    stats = get_weekly_engagement_stats(history)
    if stats["reply_prompt"] < 2:
        return "reply_prompt"
    if stats["quotable"] < 1:
        return "quotable"
    return "informational"


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


def get_recent_x_themes(history: dict, days: int = 14) -> list:
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    return [
        p["theme"]
        for p in history.get("x_posts", [])
        if datetime.datetime.fromisoformat(p["date"]) > cutoff
    ]


def get_recent_note_titles(history: dict) -> list:
    return [a["title"] for a in history.get("note_articles", [])[-10:]]


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
    """指定時間帯のX投稿を1本生成して返す。
    {"theme": ..., "content": ..., "hashtags": [...], "full_post": ...,
     "hook_id": ..., "engagement_type": ...}
    """
    history = load_history()
    recent_themes = get_recent_x_themes(history)

    available = [t for t in X_THEMES if t not in recent_themes]
    if not available:
        available = X_THEMES[:]

    # ① トレンド取得
    trends = get_google_trends()
    trend_keywords = get_related_trend_keywords(trends, available[0])

    # ② エンゲージメントタイプ・フック決定
    engagement_type = decide_engagement_type(history)
    hook = select_hook(history)

    time_desc = TIME_SLOTS.get(time_hour, "")
    slot_detail = _TIME_SLOT_DETAILS.get(time_hour, {})
    available_str = "\n".join(f"・{t}" for t in available[:6])
    recent_str = ("・" + "\n・".join(recent_themes)) if recent_themes else "なし"
    trend_str = "・" + "\n・".join(trend_keywords) if trend_keywords else "なし"

    # ③ エンゲージメントタイプ別の追加指示
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
    }.get(engagement_type, "")

    # ④ バズパターン取得（エンゲージメントタイプを考慮）
    buzz_context = build_buzz_context(available[0], engagement_type)

    # ⑤ 時間帯詳細ガイダンス
    time_guide = (
        f"【{time_hour}時の読者プロフィール】{slot_detail.get('persona', time_desc)}\n"
        f"【文字数の目安】{slot_detail.get('length_guide', '100〜140文字')}\n"
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
                    f"【最近使ったテーマ（重複禁止）】\n{recent_str}\n\n"
                    f"【使えるテーマ候補（この中から1つ選ぶ）】\n{available_str}\n\n"
                    f"【今日のトレンドキーワード（自然に盛り込む）】\n{trend_str}\n\n"
                    f"{time_guide}\n\n"
                    f"{engagement_guide}\n\n"
                    f"【今回のフック（最初の一文に使う）】\n「{hook['text']}」（{hook['style']}）\n\n"
                    f"{buzz_context}\n\n"
                    "【必須ルール】\n"
                    "・本文は100〜110文字で生成する（ハッシュタグは別途追加されるため含めない）\n"
                    "・文章は必ず完結した形で終わる。「…」で切らない\n"
                    "・数字・具体例を必ず含める\n"
                    "・北海道特化ネタを優先\n"
                    "・絵文字は2〜3個まで\n"
                    "・宣伝臭は出さない\n"
                    "・バズパターンを1つ参考にして書く\n"
                    "・フックの文から始める（そのままでもアレンジしてもOK）\n\n"
                    "以下の形式のみで出力（余計な説明不要）:\n"
                    "THEME: 選んだテーマ\n"
                    "POST: 投稿本文"
                ),
            }
        ],
    )

    text = response.content[0].text.strip()
    logger.debug("Claude応答 (X):\n%s", text)

    theme_match = re.search(r"^THEME:\s*(.+)", text, re.MULTILINE)
    post_match = re.search(r"^POST:\s*(.+)", text, re.MULTILINE | re.DOTALL)

    theme = theme_match.group(1).strip() if theme_match else available[0]
    content = post_match.group(1).strip() if post_match else text.split("\n")[-1]

    # ⑥ ハッシュタグ選定・追記
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
    """note記事を1本生成して返す。
    Returns: {"title": ..., "content": ..., "meta_description": ..., "seo_keywords": dict}
    """
    history = load_history()
    recent_titles = get_recent_note_titles(history)

    available = [t for t in NOTE_THEMES if t not in recent_titles]
    if not available:
        available = NOTE_THEMES[:]

    theme = available[0]
    recent_str = ("・" + "\n・".join(recent_titles)) if recent_titles else "なし"
    current_year = datetime.datetime.now().year

    # ① SEOキーワードリサーチ
    seo = get_seo_keywords(theme)
    primary_kw = seo["primary"]
    longtail_kws = seo["longtail"]
    all_seo_kws = [primary_kw] + longtail_kws[:3]
    seo_kw_str = "・" + "\n・".join(all_seo_kws)

    # ② トレンドを記事に組み込む
    trends = get_google_trends()
    trend_keywords = get_related_trend_keywords(trends, theme)
    trend_str = "・" + "\n・".join(trend_keywords) if trend_keywords else "なし"

    # ③ 競合分析
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

    # ⑥ メタディスクリプション生成
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
