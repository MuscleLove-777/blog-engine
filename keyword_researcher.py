"""blog_engine - キーワードリサーチモジュール

Gemini APIを使って、ブログのジャンルに応じたトレンドキーワード提案・
ロングテール分析・競合分析・コンテンツカレンダー生成を行う。
プロンプトは外部から注入可能。
"""
import json
import logging
import time
from datetime import datetime, timedelta

from google import genai

logger = logging.getLogger(__name__)


class KeywordResearcher:
    """汎用キーワードリサーチャー

    config と prompts を注入することで、任意のジャンルに対応する。
    """

    def __init__(self, config, prompts=None):
        """Geminiクライアントを初期化する

        Args:
            config: ブログ設定モジュール
            prompts: プロンプト設定モジュール（省略可）
        """
        self.config = config
        self.prompts = prompts
        self.client = genai.Client(api_key=config.GEMINI_API_KEY)
        self.model_name = config.GEMINI_MODEL
        logger.info("KeywordResearcher を初期化しました")

    def _call_ai(self, prompt: str, max_tokens: int = 2000) -> str:
        """Gemini APIを呼び出して応答テキストを返す共通メソッド（レートリミット対応）"""
        fallback_model = getattr(self.config, "GEMINI_FALLBACK_MODEL", "gemini-2.0-flash")
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
        return keywords

    def suggest_long_tail_keywords(self, base_keyword: str) -> list[str]:
        """ベースキーワードからロングテールキーワードを提案する"""
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
        return keywords

    def analyze_competition(self, keyword: str) -> dict:
        """指定キーワードの競合分析をAIで行う"""
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
        return analysis

    def get_content_calendar(self, days: int = 7) -> list[dict]:
        """指定日数分のコンテンツカレンダーを生成する"""
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
        return calendar
