"""blog_engine - キーワードリサーチモジュール

Gemini APIを使って、ブログのジャンルに応じたトレンドキーワード提案・
ロングテール分析・競合分析・コンテンツカレンダー生成を行う。
プロンプトは外部から注入可能。
"""
import hashlib
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

from blog_engine.llm import get_llm_client

logger = logging.getLogger(__name__)


class _KeywordCache:
    """キーワードリサーチ結果の24時間キャッシュ

    キャッシュはJSON形式でファイルに保存され、24時間で自動的に無効化される。
    """

    CACHE_TTL_HOURS = 24

    def __init__(self, cache_dir: str | None = None):
        self._cache_dir = Path(cache_dir) if cache_dir else Path.home() / ".cache" / "blog_engine"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_file = self._cache_dir / "keyword_cache.json"
        self._cache: dict = self._load()

    def _load(self) -> dict:
        """キャッシュファイルを読み込む"""
        if self._cache_file.exists():
            try:
                with open(self._cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                logger.warning("キャッシュファイルの読み込みに失敗。新規作成します")
        return {}

    def _save(self):
        """キャッシュをファイルに書き出す"""
        try:
            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.warning("キャッシュ保存失敗: %s", e)

    @staticmethod
    def _make_key(method: str, *args) -> str:
        """メソッド名と引数からキャッシュキーを生成する"""
        raw = json.dumps({"m": method, "a": args}, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, method: str, *args):
        """キャッシュから取得する。期限切れまたは存在しない場合は None"""
        key = self._make_key(method, *args)
        entry = self._cache.get(key)
        if entry is None:
            return None
        cached_at = datetime.fromisoformat(entry["cached_at"])
        if datetime.now() - cached_at > timedelta(hours=self.CACHE_TTL_HOURS):
            del self._cache[key]
            self._save()
            logger.debug("キャッシュ期限切れ: %s(%s)", method, args)
            return None
        logger.info("キャッシュヒット: %s(%s)", method, args)
        return entry["data"]

    def set(self, data, method: str, *args):
        """キャッシュに保存する"""
        key = self._make_key(method, *args)
        self._cache[key] = {
            "cached_at": datetime.now().isoformat(),
            "data": data,
        }
        self._save()


class KeywordResearcher:
    """汎用キーワードリサーチャー（Gemini / Claude CLI を LLM_BACKEND で切替）"""

    def __init__(self, config, prompts=None):
        self.config = config
        self.prompts = prompts
        self.client = get_llm_client(config)
        self.model_name = config.GEMINI_MODEL
        self._cache = _KeywordCache(cache_dir)
        logger.info("KeywordResearcher を初期化しました")

    def _call_ai(self, prompt: str, max_tokens: int = 2000) -> str:
        """Gemini APIを呼び出して応答テキストを返す共通メソッド（レートリミット対応）"""
        fallback_model = getattr(self.config, "GEMINI_FALLBACK_MODEL", "gemini-2.5-flash-lite")
        models_to_try = [self.model_name]
        if fallback_model and fallback_model != self.model_name:
            models_to_try.append(fallback_model)

        for model_name in models_to_try:
            for attempt in range(1, 4):
                try:
                    response = self.client.models.generate_content(
                        model=model_name, contents=prompt
                    )
                    return response.text.strip()
                except Exception as api_err:
                    err_str = str(api_err)
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        if attempt < 3:
                            wait = 30 * attempt
                            logger.warning("レートリミット検出（%s）、%d秒待機（試行%d/3）", model_name, wait, attempt)
                            time.sleep(wait)
                            continue
                        else:
                            logger.warning("モデル %s でレートリミット超過、次のモデルを試行", model_name)
                            break
                    raise

        raise RuntimeError("全モデルでレートリミット超過。時間を置いて再実行してください。")

    def _parse_json_response(self, response_text: str):
        """AIレスポンスからJSONを抽出してパースする"""
        text = response_text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        return json.loads(text)

    def _get_extra_prompt(self) -> str:
        """prompts.py から追加プロンプトを取得する"""
        if self.prompts and hasattr(self.prompts, "KEYWORD_PROMPT_EXTRA"):
            return self.prompts.KEYWORD_PROMPT_EXTRA
        return ""

    def research_trending_keywords(
        self, category: str, count: int = 10
    ) -> list[dict]:
        """トレンドキーワードをAIで提案する

        Args:
            category: 対象カテゴリ
            count: 提案するキーワード数

        Returns:
            list[dict]: 各キーワードの情報を含むリスト
        """
        cached = self._cache.get("research_trending_keywords", category, count)
        if cached is not None:
            return cached

        logger.info("トレンドキーワードをリサーチ中: カテゴリ=%s, 件数=%d", category, count)

        blog_name = self.config.BLOG_NAME
        extra = self._get_extra_prompt()

        prompt = (
            f"「{blog_name}」というブログの「{category}」カテゴリで、"
            f"現在トレンドになっているブログ記事キーワードを{count}個提案してください。\n\n"
            f"{extra}\n\n" if extra else ""
            f"各キーワードについて以下の情報を含めてください:\n"
            "- keyword: キーワード\n"
            "- volume: 検索ボリューム予測（「高」「中」「低」のいずれか）\n"
            "- competition: 競合度予測（「高」「中」「低」のいずれか）\n"
            "- article_type: 推奨記事タイプ（例: 解説、比較、トレンド分析、まとめ）\n\n"
            "JSON配列形式のみで回答してください（説明不要）:\n"
            '[{"keyword": "...", "volume": "...", "competition": "...", "article_type": "..."}]'
        )

        response = self._call_ai(prompt)
        keywords = self._parse_json_response(response)
        logger.info("%d件のキーワードを取得しました", len(keywords))
        self._cache.set(keywords, "research_trending_keywords", category, count)
        return keywords

    def suggest_long_tail_keywords(self, base_keyword: str) -> list[str]:
        """ベースキーワードからロングテールキーワードを提案する"""
        cached = self._cache.get("suggest_long_tail_keywords", base_keyword)
        if cached is not None:
            return cached

        logger.info("ロングテールキーワードを提案中: %s", base_keyword)

        blog_desc = self.config.BLOG_DESCRIPTION

        prompt = (
            f"「{base_keyword}」をベースに、"
            f"「{blog_desc}」向けブログ記事で狙えるロングテールキーワードを10個提案してください。\n\n"
            "検索意図が明確で、記事が書きやすいものを優先してください。\n\n"
            "JSON配列形式（文字列の配列）のみで回答してください（説明不要）:\n"
            '["キーワード1", "キーワード2", ...]'
        )

        response = self._call_ai(prompt)
        keywords = self._parse_json_response(response)
        logger.info("%d件のロングテールキーワードを取得しました", len(keywords))
        self._cache.set(keywords, "suggest_long_tail_keywords", base_keyword)
        return keywords

    def analyze_competition(self, keyword: str) -> dict:
        """指定キーワードの競合分析をAIで行う"""
        cached = self._cache.get("analyze_competition", keyword)
        if cached is not None:
            return cached

        logger.info("競合分析を実行中: %s", keyword)

        prompt = (
            f"「{keyword}」というキーワードでブログ記事を書く場合の"
            "競合分析を行ってください。\n\n"
            "以下の項目を含むJSON形式のみで回答してください（説明不要）:\n"
            "{\n"
            '  "keyword": "対象キーワード",\n'
            '  "difficulty": 難易度（1-10の数値）,\n'
            '  "top_content_types": ["上位表示されやすいコンテンツタイプ"],\n'
            '  "recommended_word_count": 推奨文字数（数値）,\n'
            '  "key_topics": ["記事に含めるべきトピック"],\n'
            '  "differentiation_tips": ["差別化のポイント"]\n'
            "}"
        )

        response = self._call_ai(prompt)
        analysis = self._parse_json_response(response)
        logger.info("競合分析完了: 難易度=%s", analysis.get("difficulty", "不明"))
        self._cache.set(analysis, "analyze_competition", keyword)
        return analysis

    def research_keywords_comprehensive(
        self, category: str, count: int = 10
    ) -> dict:
        """トレンドキーワード提案・ロングテール・競合分析を1回のAPI呼出で統合実行する

        従来 research_trending_keywords, suggest_long_tail_keywords,
        analyze_competition を個別に呼ぶと3回のAPI呼出が必要だったが、
        このメソッドは1回のAPI呼出で全てをまとめて取得する。

        Args:
            category: 対象カテゴリ
            count: 提案するトレンドキーワード数

        Returns:
            dict: {
                "trending_keywords": [...],    # トレンドキーワード一覧
                "long_tail_keywords": {...},    # 各キーワードのロングテール候補
                "competition_analysis": {...},  # 各キーワードの競合分析
            }
        """
        cached = self._cache.get("research_keywords_comprehensive", category, count)
        if cached is not None:
            return cached

        logger.info(
            "キーワード統合リサーチ開始: カテゴリ=%s, 件数=%d（API 1回で実行）",
            category, count,
        )

        blog_name = self.config.BLOG_NAME
        blog_desc = self.config.BLOG_DESCRIPTION
        extra = self._get_extra_prompt()

        prompt = (
            f"「{blog_name}」というブログの「{category}」カテゴリについて、"
            f"以下の3つの分析をまとめて行ってください。\n\n"
        )
        if extra:
            prompt += f"{extra}\n\n"
        prompt += (
            f"## 1. トレンドキーワード提案\n"
            f"現在トレンドになっているブログ記事キーワードを{count}個提案してください。\n"
            "各キーワードに keyword, volume（高/中/低）, competition（高/中/低）, "
            "article_type を含めてください。\n\n"
            f"## 2. ロングテールキーワード\n"
            f"上記で提案した各キーワードに対し、「{blog_desc}」向けブログで狙える"
            "ロングテールキーワードをそれぞれ5個提案してください。\n\n"
            f"## 3. 競合分析\n"
            "上記の各キーワードについて、difficulty（1-10）, top_content_types, "
            "recommended_word_count, key_topics, differentiation_tips を分析してください。\n\n"
            "以下のJSON形式のみで回答してください（説明不要）:\n"
            "{\n"
            '  "trending_keywords": [\n'
            '    {"keyword": "...", "volume": "...", "competition": "...", "article_type": "..."}\n'
            "  ],\n"
            '  "long_tail_keywords": {\n'
            '    "キーワード名": ["ロングテール1", "ロングテール2", ...]\n'
            "  },\n"
            '  "competition_analysis": {\n'
            '    "キーワード名": {\n'
            '      "difficulty": 数値,\n'
            '      "top_content_types": ["..."],\n'
            '      "recommended_word_count": 数値,\n'
            '      "key_topics": ["..."],\n'
            '      "differentiation_tips": ["..."]\n'
            "    }\n"
            "  }\n"
            "}"
        )

        response = self._call_ai(prompt, max_tokens=4000)
        result = self._parse_json_response(response)

        # 統合結果の各部分を個別メソッドのキャッシュにも保存する
        if "trending_keywords" in result:
            self._cache.set(
                result["trending_keywords"],
                "research_trending_keywords", category, count,
            )
        if "long_tail_keywords" in result:
            for kw, lt_list in result["long_tail_keywords"].items():
                self._cache.set(lt_list, "suggest_long_tail_keywords", kw)
        if "competition_analysis" in result:
            for kw, analysis in result["competition_analysis"].items():
                analysis["keyword"] = kw
                self._cache.set(analysis, "analyze_competition", kw)

        self._cache.set(result, "research_keywords_comprehensive", category, count)
        logger.info(
            "キーワード統合リサーチ完了: トレンド%d件, ロングテール%d件, 競合分析%d件",
            len(result.get("trending_keywords", [])),
            len(result.get("long_tail_keywords", {})),
            len(result.get("competition_analysis", {})),
        )
        return result

    def get_content_calendar(self, days: int = 7) -> list[dict]:
        """指定日数分のコンテンツカレンダーを生成する"""
        cached = self._cache.get("get_content_calendar", days)
        if cached is not None:
            return cached

        logger.info("コンテンツカレンダーを生成中: %d日分", days)

        start_date = datetime.now()
        dates = [
            (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(days)
        ]
        dates_text = "\n".join(f"- {d}" for d in dates)
        categories_text = "\n".join(
            f"- {cat}" for cat in self.config.TARGET_CATEGORIES
        )
        extra = self._get_extra_prompt()

        prompt = (
            f"「{self.config.BLOG_NAME}」のコンテンツカレンダーを作成してください。\n\n"
            f"{extra}\n\n" if extra else ""
            f"日付:\n{dates_text}\n\n"
            f"カテゴリ:\n{categories_text}\n\n"
            "各日付に対して、カテゴリをバランスよく配分し、"
            "トレンドを意識したキーワードと記事タイプを設定してください。\n\n"
            "JSON配列形式のみで回答してください（説明不要）:\n"
            '[{"date": "YYYY-MM-DD", "keyword": "...", '
            '"category": "...", "article_type": "..."}]'
        )

        response = self._call_ai(prompt, max_tokens=3000)
        calendar = self._parse_json_response(response)
        logger.info("コンテンツカレンダー生成完了: %d件", len(calendar))
        self._cache.set(calendar, "get_content_calendar", days)
        return calendar
