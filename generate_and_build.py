"""blog_engine - GitHub Actions用一括実行スクリプト

各ブログのconfig.pyとprompts.pyを受け取って、
キーワード選定 → 記事生成 → サイトビルドを一括実行する。
"""
import json
import logging
import sys
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
        from google import genai

        if not config.GEMINI_API_KEY:
            logger.error("GEMINI_API_KEY が設定されていません")
            sys.exit(1)

        client = genai.Client(api_key=config.GEMINI_API_KEY)

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

        response = client.models.generate_content(
            model=config.GEMINI_MODEL, contents=prompt
        )
        response_text = response.text.strip()

        if "```" in response_text:
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        data = json.loads(response_text)
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
