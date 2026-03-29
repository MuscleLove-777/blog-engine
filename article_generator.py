"""blog_engine - 記事生成エンジン

Gemini APIを使用してSEO最適化されたブログ記事を自動生成する共通モジュール。
各ブログのprompts.pyからプロンプトを取得し、config.pyの設定に基づいて記事を生成する。
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from google import genai

logger = logging.getLogger(__name__)


class ArticleGenerator:
    """Gemini APIを使ったブログ記事生成エンジン"""

    def __init__(self, config) -> None:
        if not config.GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY が設定されていません。"
                "環境変数 GEMINI_API_KEY を設定してください。"
            )

        self.config = config
        self.client = genai.Client(api_key=config.GEMINI_API_KEY)
        self.model_name = config.GEMINI_MODEL

        self.articles_dir = Path(config.BASE_DIR) / "output" / "articles"
        self.articles_dir.mkdir(parents=True, exist_ok=True)

        logger.info("ArticleGenerator を初期化しました（モデル: %s）", config.GEMINI_MODEL)

    def generate_article(self, keyword: str, category: str, prompts=None) -> dict:
        """キーワードとカテゴリからSEO最適化されたブログ記事を生成する"""
        logger.info("記事生成を開始: キーワード='%s', カテゴリ='%s'", keyword, category)

        if prompts and hasattr(prompts, 'build_article_prompt'):
            prompt = prompts.build_article_prompt(keyword, category, self.config)
        else:
            prompt = self._build_default_prompt(keyword, category)

        try:
            from google.genai import types
            gen_config = types.GenerateContentConfig(
                max_output_tokens=16384,
                response_mime_type="application/json",
            )
            response = self.client.models.generate_content(
                model=self.model_name, contents=prompt, config=gen_config
            )
            response_text = response.text
            logger.debug("APIレスポンスを受信（%d文字）", len(response_text))
        except Exception as e:
            logger.error("Gemini API呼び出しに失敗: %s", e)
            raise

        article = self._parse_response(response_text)
        article["keyword"] = keyword
        article["category"] = category
        article["generated_at"] = datetime.now().isoformat()

        file_path = self._save_article(article)
        article["file_path"] = str(file_path)

        logger.info("記事生成完了: '%s' → %s", article["title"], file_path)
        return article

    def _build_default_prompt(self, keyword: str, category: str) -> str:
        config = self.config
        return f"""あなたはSEOに精通したプロのブログライターです。
以下の条件に従って、高品質なブログ記事を生成してください。

【基本条件】
- ブログ名: {config.BLOG_NAME}
- キーワード: {keyword}
- カテゴリ: {category}
- 言語: 日本語
- 文字数目安: {config.MAX_ARTICLE_LENGTH}文字程度

【SEO要件】
1. タイトルにキーワード「{keyword}」を必ず含めること
2. タイトルは32文字以内で魅力的に
3. H2、H3の見出し構造を適切に使用すること
4. メタディスクリプションは120文字以内
5. 内部リンクのプレースホルダーを2〜3箇所に配置（{{{{internal_link:関連トピック}}}}の形式）

【記事構成】
1. 導入（読者の関心を引く問いかけやデータ）
2. 本文（H2で3〜5セクション、必要に応じてH3を使用）
3. まとめ（要点整理と次のアクション提案）

【出力形式】
以下のJSON形式で出力してください。JSONブロック以外のテキストは出力しないでください。

```json
{{
  "title": "SEO最適化されたタイトル",
  "content": "# タイトル\n\n本文（Markdown形式）...",
  "meta_description": "120文字以内のメタディスクリプション",
  "tags": ["タグ1", "タグ2", "タグ3", "タグ4", "タグ5"],
  "slug": "url-friendly-slug"
}}
```

【注意事項】
- content内のMarkdownは適切にエスケープしてJSON文字列として有効にすること
- tagsは5個ちょうど生成すること
- slugは半角英数字とハイフンのみ使用すること"""

    @staticmethod
    def _fix_json_control_chars(text: str) -> str:
        """JSON文字列内の不正な制御文字を修正する"""
        # JSON文字列値内の生の改行・タブをエスケープシーケンスに置換
        import re as _re
        def _fix_match(m):
            s = m.group(0)
            s = s.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
            # その他の制御文字を除去
            s = _re.sub(r'[\x00-\x1f]', '', s)
            return s
        # JSON文字列値（ダブルクォートで囲まれた部分）を検出して修正
        return _re.sub(r'"(?:[^"\\]|\\.)*"', _fix_match, text, flags=_re.DOTALL)

    def _parse_response(self, response_text: str) -> dict:
        json_match = re.search(
            r"```json\s*(.*?)\s*```", response_text, re.DOTALL
        )

        try:
            if json_match:
                raw = json_match.group(1)
            else:
                cleaned = response_text.strip()
                start = cleaned.find("{")
                end = cleaned.rfind("}") + 1
                if start >= 0 and end > start:
                    raw = cleaned[start:end]
                else:
                    raw = cleaned
            # 制御文字を修正してからパース
            raw = self._fix_json_control_chars(raw)
            article_data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(
                "JSONパースに失敗: %s\nレスポンス先頭200文字: %s",
                e, response_text[:200],
            )
            raise ValueError(
                f"APIレスポンスのJSONパースに失敗しました: {e}"
            ) from e

        required_fields = ["title", "content", "meta_description", "tags", "slug"]
        missing = [f for f in required_fields if f not in article_data]
        if missing:
            raise ValueError(
                f"APIレスポンスに必須フィールドが不足しています: {missing}"
            )

        if not isinstance(article_data["tags"], list):
            article_data["tags"] = [article_data["tags"]]

        article_data["slug"] = re.sub(
            r"[^a-z0-9-]", "", article_data["slug"].lower().replace(" ", "-")
        )

        return article_data

    def _save_article(self, article: dict) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = article.get("slug", "untitled")
        filename = f"{timestamp}_{slug}.json"
        file_path = self.articles_dir / filename

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(article, f, ensure_ascii=False, indent=2)

        logger.info("記事を保存しました: %s", file_path)
        return file_path
