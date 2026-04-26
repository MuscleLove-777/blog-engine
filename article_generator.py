"""blog_engine - 記事生成エンジン

Gemini APIを使用してSEO最適化されたブログ記事を自動生成する共通モジュール。
各ブログのprompts.pyからプロンプトを取得し、config.pyの設定に基づいて記事を生成する。
"""

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path

from blog_engine.llm import get_llm_client

logger = logging.getLogger(__name__)


class ArticleGenerator:
    """ブログ記事生成エンジン（Gemini / Claude Code CLI を LLM_BACKEND で切替）"""

    def __init__(self, config) -> None:
        self.config = config
        self.client = get_llm_client(config)
        self.model_name = config.GEMINI_MODEL

        self.articles_dir = Path(config.BASE_DIR) / "output" / "articles"
        self.articles_dir.mkdir(parents=True, exist_ok=True)

        logger.info("ArticleGenerator を初期化しました（モデル: %s）", config.GEMINI_MODEL)

    def generate_article(self, keyword: str, category: str, prompts=None) -> dict:
        """キーワードとカテゴリからSEO最適化されたブログ記事を生成する（最大5回リトライ）"""
        logger.info("記事生成を開始: キーワード='%s', カテゴリ='%s'", keyword, category)

        if prompts and hasattr(prompts, 'build_article_prompt'):
            prompt = prompts.build_article_prompt(keyword, category, self.config)
        else:
            prompt = self._build_default_prompt(keyword, category)

        max_retries = 5
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                try:
                    from google.genai import types
                    gen_config = types.GenerateContentConfig(
                        max_output_tokens=65536,
                        response_mime_type="application/json",
                    )
                except ImportError:
                    gen_config = None  # Claude shim 経由など google-genai 不在時
                # レートリミット対策: フォールバックモデルも試す
                fallback_model = getattr(self.config, "GEMINI_FALLBACK_MODEL", "gemini-2.5-flash-lite")
                models_to_try = [self.model_name]
                if fallback_model and fallback_model != self.model_name:
                    models_to_try.append(fallback_model)

                api_success = False
                for model_name in models_to_try:
                    for api_attempt in range(1, 4):
                        try:
                            response = self.client.models.generate_content(
                                model=model_name, contents=prompt, config=gen_config
                            )
                            response_text = response.text
                            logger.debug("APIレスポンスを受信（%d文字、モデル: %s）", len(response_text), model_name)
                            api_success = True
                            break
                        except Exception as api_err:
                            err_str = str(api_err)
                            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                                if api_attempt < 3:
                                    wait = 30 * api_attempt
                                    logger.warning("レートリミット検出（%s）、%d秒待機（試行%d/3）", model_name, wait, api_attempt)
                                    time.sleep(wait)
                                    continue
                                else:
                                    logger.warning("モデル %s でレートリミット超過、次のモデルを試行", model_name)
                                    break
                            raise
                    if api_success:
                        break

                if not api_success:
                    raise RuntimeError("全モデルでレートリミット超過。時間を置いて再実行してください。")
            except RuntimeError:
                raise
            except Exception as e:
                logger.error("Gemini API呼び出しに失敗: %s", e)
                raise

            try:
                article = self._parse_response(response_text)
                break
            except (json.JSONDecodeError, ValueError) as e:
                last_error = e
                if attempt < max_retries:
                    logger.warning("JSONパース失敗（試行%d/%d）、リトライします: %s", attempt, max_retries, e)
                    time.sleep(2 * attempt)
                else:
                    logger.error("JSONパースに失敗: %s", e)
                    raise ValueError(f"JSONパースに失敗: {e}") from e

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

【ビジュアル要件】
- 各H2セクションの冒頭に、内容を象徴する絵文字アイコンを付けること（例: ## 🔍 キーワード選定のコツ）
- 本文中に「ポイント」「注意」「まとめ」などの強調ボックスをMarkdownの引用（>）で表現すること
  - > 💡 **ポイント**: 〜
  - > ⚠️ **注意**: 〜
  - > ✅ **まとめ**: 〜
- 本文中に比較表やステップ表をMarkdownテーブルで積極的に使うこと
- 箇条書きだけでなく、番号付きリストも適宜使い分けること

【出力形式】
以下のJSON形式で出力してください。JSONブロック以外のテキストは出力しないでください。

```json
{{
  "title": "SEO最適化されたタイトル",
  "content": "# タイトル\n\n本文（Markdown形式）...",
  "meta_description": "120文字以内のメタディスクリプション",
  "tags": ["タグ1", "タグ2", "タグ3", "タグ4", "タグ5"],
  "slug": "url-friendly-slug",
  "hero_emoji": "記事テーマを象徴する絵文字1つ（例: 🚀）",
  "hero_gradient": "CSSグラデーション方向キーワード（135deg, 45deg, 90deg, 180degのいずれか）"
}}
```

【注意事項】
- content内のMarkdownは適切にエスケープしてJSON文字列として有効にすること
- tagsは5個ちょうど生成すること
- slugは半角英数字とハイフンのみ使用すること
- hero_emojiは記事の内容を最もよく表す絵文字を1つだけ選ぶこと
- 各H2見出しには必ず絵文字を先頭に付けること"""

    @staticmethod
    def _fix_json_control_chars(text: str) -> str:
        """JSON文字列内の不正な制御文字を修正する"""
        import re as _re
        def _fix_match(m):
            s = m.group(0)
            s = s.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
            s = _re.sub(r'[\x00-\x1f]', '', s)
            return s
        return _re.sub(r'"(?:[^"\\]|\\.)*"', _fix_match, text, flags=_re.DOTALL)

    @staticmethod
    def _repair_json(text: str) -> str:
        """壊れたJSONを修復する（Geminiの長文生成で発生しがちな問題に対応）"""
        # 1. BOMや不可視文字を除去
        text = text.strip().lstrip('\ufeff')
        # 2. ```json ... ``` ブロックを除去
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            text = json_match.group(1)
        # 3. JSONオブジェクト部分を抽出
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            text = text[start:end]
        # 4. 文字列値内の生の改行をエスケープ
        result = []
        in_string = False
        escape_next = False
        for ch in text:
            if escape_next:
                result.append(ch)
                escape_next = False
                continue
            if ch == '\\' and in_string:
                result.append(ch)
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                result.append(ch)
                continue
            if in_string:
                if ch == '\n':
                    result.append('\\n')
                elif ch == '\r':
                    result.append('\\r')
                elif ch == '\t':
                    result.append('\\t')
                elif ord(ch) < 0x20:
                    pass  # 制御文字を除去
                else:
                    result.append(ch)
            else:
                result.append(ch)
        repaired = ''.join(result)

        # 5. 切り詰められたJSONを閉じる（Unterminated string対策）
        # 開いたままの文字列を閉じ、不足するブラケットを補完
        open_braces = repaired.count('{') - repaired.count('}')
        open_brackets = repaired.count('[') - repaired.count(']')
        if open_braces > 0 or open_brackets > 0:
            # 未閉じの文字列があれば閉じる
            if in_string:
                repaired += '"'
            repaired += ']' * max(open_brackets, 0)
            repaired += '}' * max(open_braces, 0)

        # 6. それでもパースできない場合、フィールド単位で抽出を試みる
        try:
            json.loads(repaired, strict=False)
        except json.JSONDecodeError:
            extracted = ArticleGenerator._extract_fields_fallback(repaired)
            if extracted:
                repaired = json.dumps(extracted, ensure_ascii=False)

        return repaired

    @staticmethod
    def _extract_fields_fallback(text: str) -> dict:
        """JSONパースが完全に失敗した場合、正規表現でフィールドを個別抽出する"""
        result = {}
        # title
        m = re.search(r'"title"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
        if m:
            result["title"] = m.group(1).replace('\\"', '"')
        # meta_description
        m = re.search(r'"meta_description"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
        if m:
            result["meta_description"] = m.group(1).replace('\\"', '"')
        # slug
        m = re.search(r'"slug"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
        if m:
            result["slug"] = m.group(1).replace('\\"', '"')
        # hero_emoji
        m = re.search(r'"hero_emoji"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
        if m:
            result["hero_emoji"] = m.group(1).replace('\\"', '"')
        # hero_gradient
        m = re.search(r'"hero_gradient"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
        if m:
            result["hero_gradient"] = m.group(1).replace('\\"', '"')
        # tags - 配列を抽出
        m = re.search(r'"tags"\s*:\s*\[(.*?)\]', text, re.DOTALL)
        if m:
            tags_raw = m.group(1)
            tags = re.findall(r'"((?:[^"\\]|\\.)*)"', tags_raw)
            result["tags"] = tags
        # faq - 配列を抽出
        m = re.search(r'"faq"\s*:\s*\[(.+)\]', text, re.DOTALL)
        if m:
            faq_raw = m.group(1)
            questions = re.findall(r'"question"\s*:\s*"((?:[^"\\]|\\.)*)"', faq_raw)
            answers = re.findall(r'"answer"\s*:\s*"((?:[^"\\]|\\.)*)"', faq_raw)
            result["faq"] = [
                {"question": q.replace('\\"', '"'), "answer": a.replace('\\"', '"')}
                for q, a in zip(questions, answers)
            ]
        # content - 最も長い文字列値をcontentとして扱う（最後の手段）
        m = re.search(r'"content"\s*:\s*"', text)
        if m:
            # contentの開始位置から、次の有効なJSONキーまでを抽出
            start_pos = m.end()
            # 文字列終端を探す（エスケープされていない"を探す）
            pos = start_pos
            content_chars = []
            while pos < len(text):
                ch = text[pos]
                if ch == '\\' and pos + 1 < len(text):
                    content_chars.append(ch)
                    content_chars.append(text[pos + 1])
                    pos += 2
                    continue
                if ch == '"':
                    break
                content_chars.append(ch)
                pos += 1
            result["content"] = ''.join(content_chars).replace('\\"', '"').replace('\\n', '\n')

        if result:
            logger.warning("フォールバック抽出で%d個のフィールドを回収: %s",
                          len(result), list(result.keys()))
        return result

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
            article_data = json.loads(raw, strict=False)
        except json.JSONDecodeError as e1:
            logger.warning("JSONパース初回失敗、修復を試行: %s", e1)
            try:
                repaired = self._repair_json(response_text)
                article_data = json.loads(repaired, strict=False)
                logger.info("JSON修復に成功しました")
            except json.JSONDecodeError as e2:
                logger.error(
                    "JSON修復後もパースに失敗: %s\nレスポンス先頭200文字: %s",
                    e2, response_text[:200],
                )
                raise ValueError(
                    f"APIレスポンスのJSONパースに失敗しました: {e2}"
                ) from e2

        # 必須フィールドが欠落している場合はデフォルト値で補完
        article_data.setdefault("hero_emoji", "📝")
        article_data.setdefault("hero_gradient", "135deg")

        # titleとcontentは最低限必要（これがないと記事として成立しない）
        if "title" not in article_data and "content" not in article_data:
            raise ValueError(
                "APIレスポンスにtitleとcontentの両方が不足しています"
            )

        # 補完可能なフィールドにデフォルト値を設定
        if "title" not in article_data:
            # contentの先頭行からタイトルを抽出
            content = article_data.get("content", "")
            first_line = content.split("\n")[0].lstrip("# ").strip()
            article_data["title"] = first_line or "無題の記事"
            logger.warning("titleが欠落 → contentから補完: %s", article_data["title"])

        if "content" not in article_data:
            article_data["content"] = f"# {article_data['title']}\n\n記事の内容を生成できませんでした。"
            logger.warning("contentが欠落 → デフォルト値を設定")

        if "meta_description" not in article_data:
            # contentの先頭120文字をメタディスクリプションとして使用
            content_text = re.sub(r'[#*\[\]()]', '', article_data["content"])
            article_data["meta_description"] = content_text[:120].strip()
            logger.warning("meta_descriptionが欠落 → contentから自動生成")

        if "tags" not in article_data:
            article_data["tags"] = ["自動生成", "ブログ", "記事", "SEO", "最新"]
            logger.warning("tagsが欠落 → デフォルト値を設定")

        if "slug" not in article_data:
            # タイトルからslugを生成（日本語はハイフンに変換）
            slug = re.sub(r'[^a-zA-Z0-9\s-]', '', article_data["title"].lower())
            slug = re.sub(r'\s+', '-', slug).strip('-') or "untitled-article"
            article_data["slug"] = slug
            logger.warning("slugが欠落 → タイトルから自動生成: %s", slug)

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
