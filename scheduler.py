"""blog_engine - 記事自動生成・投稿スケジューラー

APSchedulerを使って指定時刻に記事を自動生成する。
"""
import json
import logging
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class BlogScheduler:
    """記事の自動生成スケジューラー

    config と prompts を注入して使用する。
    """

    def __init__(self, config, prompts=None):
        """APScheduler・各モジュールを初期化する

        Args:
            config: ブログ設定モジュール
            prompts: プロンプト設定モジュール（省略可）
        """
        self.config = config
        self.prompts = prompts
        self.scheduler = BlockingScheduler()

        from .article_generator import ArticleGenerator
        from .site_generator import SiteGenerator
        from .seo_optimizer import SEOOptimizer

        self.article_generator = ArticleGenerator(config, prompts)
        self.site_generator = SiteGenerator(config)
        self.seo_optimizer = SEOOptimizer(config)

        self.logs_dir = config.OUTPUT_DIR / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        logger.info("BlogScheduler を初期化しました")

    def start(self):
        """スケジューラーを開始する"""
        schedule_hours = self.config.SCHEDULE_HOURS

        for hour in schedule_hours:
            trigger = CronTrigger(hour=hour, minute=0)
            self.scheduler.add_job(
                self.run_job,
                trigger=trigger,
                id=f"blog_job_{hour}",
                name=f"記事生成ジョブ（{hour}時）",
                misfire_grace_time=3600,
            )
            logger.info("ジョブを登録: 毎日 %d:00 に記事を生成", hour)

        logger.info(
            "スケジューラーを開始します（1日%d記事、投稿時刻: %s）",
            self.config.ARTICLES_PER_DAY, schedule_hours,
        )

        try:
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("スケジューラーを停止しました")

    def stop(self):
        """スケジューラーを停止する"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("スケジューラーを停止しました")
        else:
            logger.warning("スケジューラーは実行されていません")

    def run_job(self):
        """1回分のジョブを実行する"""
        logger.info("=== ジョブ実行開始 ===")
        start_time = datetime.now()
        result = {
            "timestamp": start_time.isoformat(),
            "status": "started",
            "category": None,
            "keyword": None,
            "article_path": None,
            "seo_score": None,
            "errors": [],
        }

        try:
            # ステップ1: キーワード選定
            logger.info("ステップ1: キーワード選定中...")
            category, keyword = self._select_keyword()
            result["category"] = category
            result["keyword"] = keyword
            logger.info("選定結果 - カテゴリ: %s, キーワード: %s", category, keyword)

            # ステップ2: 記事生成
            logger.info("ステップ2: 記事生成中...")
            article = self.article_generator.generate_article(
                keyword=keyword, category=category,
            )
            result["article_path"] = str(article.get("file_path", ""))
            logger.info("記事生成完了: %s", article.get("title", "不明"))

            # ステップ2.5: アフィリエイトリンク挿入
            logger.info("ステップ2.5: アフィリエイトリンク挿入中...")
            try:
                from .affiliate import AffiliateManager
                affiliate_mgr = AffiliateManager(self.config, self.prompts)
                article = affiliate_mgr.insert_affiliate_links(article)
                logger.info("アフィリエイトリンク: %d件挿入", article.get("affiliate_count", 0))
            except Exception as aff_err:
                logger.warning("アフィリエイトリンク挿入をスキップ: %s", aff_err)

            # ステップ3: SEOチェック
            logger.info("ステップ3: SEO最適化チェック中...")
            seo_result = self.seo_optimizer.check_seo_score(article)
            result["seo_score"] = seo_result.get("total_score", 0)
            logger.info("SEOスコア: %d", result["seo_score"])

            if result["seo_score"] < 60:
                logger.warning(
                    "SEOスコアが低いです（%d）。記事の改善を検討してください。",
                    result["seo_score"],
                )

            # ステップ4: サイトビルド
            logger.info("ステップ4: サイトビルド中...")
            self.site_generator.build_site()
            logger.info("サイトビルド完了")

            # ステップ5: GitHub Pagesにデプロイ
            logger.info("ステップ5: GitHub Pagesにデプロイ中...")
            try:
                from .deployer import GitHubPagesDeployer
                deployer = GitHubPagesDeployer(self.config)
                deploy_result = deployer.deploy()
                result["deploy_status"] = deploy_result["status"]
                if "url" in deploy_result:
                    result["deploy_url"] = deploy_result["url"]
                logger.info("デプロイ結果: %s", deploy_result["status"])
            except Exception as deploy_err:
                logger.warning("デプロイをスキップ: %s", deploy_err)
                result["deploy_status"] = "skipped"

            result["status"] = "success"
            result["duration_seconds"] = (datetime.now() - start_time).total_seconds()
            logger.info("=== ジョブ完了（%.1f秒） ===", result["duration_seconds"])

        except Exception as e:
            result["status"] = "error"
            result["errors"].append(str(e))
            result["duration_seconds"] = (datetime.now() - start_time).total_seconds()
            logger.error("ジョブ実行中にエラー発生: %s", e)

        self._log_execution(result)
        return result

    def _select_keyword(self) -> tuple:
        """AIを使ってカテゴリとキーワードを選定する"""
        from google import genai

        client = genai.Client(api_key=self.config.GEMINI_API_KEY)
        categories_text = "\n".join(
            f"- {cat}" for cat in self.config.TARGET_CATEGORIES
        )

        extra = ""
        if self.prompts and hasattr(self.prompts, "KEYWORD_PROMPT_EXTRA"):
            extra = self.prompts.KEYWORD_PROMPT_EXTRA

        prompt = (
            f"「{self.config.BLOG_NAME}」用のキーワードを選定してください。\n\n"
            f"{extra}\n\n" if extra else ""
            "以下のカテゴリから1つ選び、そのカテゴリで今注目されている"
            "ブログ記事キーワードを1つ提案してください。\n\n"
            f"カテゴリ一覧:\n{categories_text}\n\n"
            "以下の形式でJSON形式のみで回答してください（説明不要）:\n"
            '{"category": "カテゴリ名", "keyword": "キーワード"}'
        )

        response = client.models.generate_content(
            model=self.config.GEMINI_MODEL, contents=prompt
        )

        response_text = response.text.strip()
        if "```" in response_text:
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        data = json.loads(response_text)
        return data["category"], data["keyword"]

    def _log_execution(self, result: dict):
        """実行ログをJSONファイルに保存する"""
        today = datetime.now().strftime("%Y%m%d")
        log_file = self.logs_dir / f"{today}.json"

        if log_file.exists():
            with open(log_file, "r", encoding="utf-8") as f:
                logs = json.load(f)
        else:
            logs = []

        logs.append(result)

        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)

        logger.info("実行ログを保存: %s", log_file)
