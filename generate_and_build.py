"""blog_engine - GitHub Actions用一括実行スクリプト

各ブログのconfig.pyとprompts.pyを受け取って、
キーワード選定 → 記事生成 → サイトビルドを一括実行する。
"""
import json
import logging
import sys
import time
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def run(config, prompts=None):
    """メイン処理: キーワード選定 → 記事生成 → サイトビルド

    Args:
        config: ブログ固有の設定モジュール
        prompts: ブログ固有のプロンプトモジュール（任意）
    """
    logger.info("=== %s 自動生成開始 ===", config.BLOG_NAME)
    start_time = datetime.now()

    # ステップ1: キーワード選定
    logger.info("ステップ1: キーワード選定")
    try:
        from blog_engine.llm import get_llm_client

        client = get_llm_client(config)

        categories_text = "\n".join(f"- {cat}" for cat in config.TARGET_CATEGORIES)

        # プロンプトモジュールにキーワード選定プロンプトがあればそれを使う
        if prompts and hasattr(prompts, "build_keyword_prompt"):
            prompt = prompts.build_keyword_prompt(config)
        else:
            prompt = (
                f"{config.BLOG_NAME}用のキーワードを選定してください。\n\n"
                "以下のカテゴリから1つ選び、そのカテゴリで今注目されている"
                "トピック・キーワードを1つ提案してください。\n\n"
                f"カテゴリ一覧:\n{categories_text}\n\n"
                "検索ボリュームの高いキーワードを意識してください。\n\n"
                "以下の形式でJSON形式のみで回答してください（説明不要）:\n"
                '{"category": "カテゴリ名", "keyword": "キーワード"}'
            )

        # レートリミット対策: プライマリモデルとフォールバックモデルを順番に試す
        fallback_model = getattr(config, "GEMINI_FALLBACK_MODEL", "gemini-2.5-flash-lite")
        models_to_try = [config.GEMINI_MODEL]
        if fallback_model and fallback_model != config.GEMINI_MODEL:
            models_to_try.append(fallback_model)

        max_retries = 3
        response_text = None
        for model_name in models_to_try:
            for attempt in range(1, max_retries + 1):
                try:
                    logger.info("モデル %s でキーワード選定を試行（%d/%d）", model_name, attempt, max_retries)
                    response = client.models.generate_content(
                        model=model_name, contents=prompt
                    )
                    response_text = response.text.strip()
                    break
                except Exception as api_err:
                    err_str = str(api_err)
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        if attempt < max_retries:
                            wait = 30 * attempt
                            logger.warning("レートリミット検出（%s）、%d秒待機（試行%d/%d）", model_name, wait, attempt, max_retries)
                            time.sleep(wait)
                            continue
                        else:
                            logger.warning("モデル %s でレートリミット超過、次のモデルを試行", model_name)
                            break
                    raise
            if response_text is not None:
                break

        if response_text is None:
            raise RuntimeError("キーワード選定のAPI呼び出しに失敗しました")

        if "```" in response_text:
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        data = json.loads(response_text)
        # Geminiがリストで返す場合があるので先頭要素を取得
        if isinstance(data, list):
            data = data[0]
        category = data["category"]
        keyword = data["keyword"]
        logger.info(f"選定結果 - カテゴリ: {category}, キーワード: {keyword}")

    except Exception as e:
        logger.error(f"キーワード選定に失敗: {e}")
        sys.exit(1)

    # ステップ2: 記事生成
    logger.info("ステップ2: 記事生成")
    try:
        from blog_engine.article_generator import ArticleGenerator
        from blog_engine.seo_optimizer import SEOOptimizer

        generator = ArticleGenerator(config)
        article = generator.generate_article(
            keyword=keyword, category=category, prompts=prompts
        )
        logger.info(f"記事生成完了: {article.get('title', '不明')}")

        optimizer = SEOOptimizer(config)
        seo_result = optimizer.check_seo_score(article)
        logger.info(f"SEOスコア: {seo_result.get('total_score', 0)}/100")

    except Exception as e:
        logger.error(f"記事生成に失敗: {e}")
        sys.exit(1)

    # ステップ2.5: アフィリエイトリンク挿入
    logger.info("ステップ2.5: アフィリエイトリンク挿入")
    try:
        from blog_engine.affiliate import AffiliateManager
        affiliate_mgr = AffiliateManager(config)
        article = affiliate_mgr.insert_affiliate_links(article)
        logger.info(f"アフィリエイトリンク: {article.get('affiliate_count', 0)}件挿入")
    except Exception as aff_err:
        logger.warning(f"アフィリエイトリンク挿入をスキップ: {aff_err}")

    # ステップ3: サイトビルド
    logger.info("ステップ3: サイトビルド")
    try:
        from blog_engine.site_generator import SiteGenerator
        site_gen = SiteGenerator(config)
        site_gen.build_site()
        logger.info("サイトビルド完了")
    except Exception as e:
        logger.error(f"サイトビルドに失敗: {e}")
        sys.exit(1)

    # 完了
    duration = (datetime.now() - start_time).total_seconds()
    logger.info(f"=== 自動生成完了（{duration:.1f}秒） ===")
    logger.info(f"  カテゴリ: {category}")
    logger.info(f"  キーワード: {keyword}")
    logger.info(f"  タイトル: {article.get('title', '不明')}")
    logger.info(f"  SEOスコア: {seo_result.get('total_score', 0)}/100")
