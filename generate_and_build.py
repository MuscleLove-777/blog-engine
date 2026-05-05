"""blog_engine - GitHub Actions用一括実行スクリプト

各ブログのconfig.pyとprompts.pyを受け取って、
キーワード選定 → 記事生成 → サイトビルドを一括実行する。
"""
import json
import logging
import sys
import time
from datetime import datetime

from blog_engine.llm import get_llm_client

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

    # ステップ1: キーワード選定（topic_collector経由で topics.json から）
    # 旧実装は Gemini に毎日「カテゴリ＋キーワード選んで」と頼んでたが、
    # Gemini がプロンプト例の例キーワードをオウム返しして同一記事量産が発生。
    # topic_collector.get_next_topic() で topics.json の優先度順に確実に順送りする。
    # 各ブログのCWDに topic_collector.py と topics.json が存在することが前提。
    logger.info("ステップ1: キーワード選定（topics.json）")
    tc = None
    try:
        from topic_collector import TopicCollector
        tc = TopicCollector(config)
        category, keyword = tc.get_next_topic()
        if not category or not keyword:
            logger.error("topics.json に未処理(pending)のトピックがありません。topics.json を補充してください。")
            sys.exit(1)
        logger.info("選定結果 - カテゴリ: %s, キーワード: %s", category, keyword)
    except SystemExit:
        raise
    except Exception as e:
        logger.error("キーワード選定に失敗: %s", e)
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

    # ステップ2.6: コンテンツ画像挿入
    logger.info("ステップ2.6: コンテンツ画像挿入")
    try:
        from blog_engine.content_image_fetcher import ContentImageFetcher
        content_fetcher = ContentImageFetcher(config)
        article = content_fetcher.fetch_and_inject(article)
        logger.info(f"コンテンツ画像: {article.get('content_image_count', 0)}枚挿入")
        # 記事JSONファイルを更新
        if article.get("file_path"):
            import json as _json2
            with open(article["file_path"], "w", encoding="utf-8") as _f2:
                _json2.dump(article, _f2, ensure_ascii=False, indent=2)
    except Exception as cimg_err:
        logger.warning(f"コンテンツ画像挿入をスキップ: {cimg_err}")

    # ステップ2.7: アイキャッチ画像取得
    logger.info("ステップ2.7: アイキャッチ画像取得")
    try:
        from blog_engine.image_fetcher import ImageFetcher
        fetcher = ImageFetcher(config)
        eyecatch_url = fetcher.fetch_eyecatch(article)
        if eyecatch_url:
            article["eyecatch_url"] = eyecatch_url
            # 記事JSONファイルを更新
            if article.get("file_path"):
                import json as _json
                with open(article["file_path"], "w", encoding="utf-8") as _f:
                    _json.dump(article, _f, ensure_ascii=False, indent=2)
            logger.info("アイキャッチ画像: %s", eyecatch_url)
        else:
            logger.info("アイキャッチ画像: CSSグラデーションを使用")
    except Exception as img_err:
        logger.warning("画像取得スキップ: %s", img_err)

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

    # ステップ4: トピックを done にして topics.json を更新（次回の重複防止）
    if tc is not None:
        try:
            tc.mark_as_done(category, keyword)
            logger.info("トピックを done に更新: [%s] %s", category, keyword)
        except Exception as e:
            logger.warning("topics.json の更新をスキップ: %s", e)

    # 完了
    duration = (datetime.now() - start_time).total_seconds()
    logger.info(f"=== 自動生成完了（{duration:.1f}秒） ===")
    logger.info(f"  カテゴリ: {category}")
    logger.info(f"  キーワード: {keyword}")
    logger.info(f"  タイトル: {article.get('title', '不明')}")
    logger.info(f"  SEOスコア: {seo_result.get('total_score', 0)}/100")
