"""blog_engine - CLIエントリポイント

configパスを引数で受け取り、各コマンドを実行する。

使い方:
    python -m blog_engine.main --config blogs/ai-tools/config.py generate --keyword "AI" --category "AI"
    python -m blog_engine.main --config blogs/ai-tools/config.py build
    python -m blog_engine.main --config blogs/ai-tools/config.py deploy
    python -m blog_engine.main --config blogs/ai-tools/config.py schedule
    python -m blog_engine.main --config blogs/ai-tools/config.py keywords --category "AI"
    python -m blog_engine.main --config blogs/ai-tools/config.py calendar --days 7
    python -m blog_engine.main --config blogs/ai-tools/config.py dashboard
"""
import argparse
import importlib.util
import json
import logging
import sys
from pathlib import Path

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def load_module(filepath: str, module_name: str):
    """ファイルパスからPythonモジュールを動的にロードする

    Args:
        filepath: .py ファイルのパス
        module_name: 登録するモジュール名

    Returns:
        ロードされたモジュールオブジェクト
    """
    path = Path(filepath).resolve()
    if not path.exists():
        print(f"エラー: ファイルが見つかりません: {path}")
        sys.exit(1)

    spec = importlib.util.spec_from_file_location(module_name, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def ensure_dirs(config):
    """configに必要なディレクトリ属性がなければ作る"""
    base_dir = getattr(config, "BASE_DIR", Path(config.__file__).parent if hasattr(config, "__file__") else Path.cwd())

    if not hasattr(config, "OUTPUT_DIR"):
        config.OUTPUT_DIR = base_dir / "output"
    if not hasattr(config, "ARTICLES_DIR"):
        config.ARTICLES_DIR = config.OUTPUT_DIR / "articles"
    if not hasattr(config, "SITE_DIR"):
        config.SITE_DIR = config.OUTPUT_DIR / "site"


# ==============================================================
# コマンドハンドラー
# ==============================================================

def cmd_generate(args, config, prompts):
    """単発で記事を生成する"""
    from blog_engine.article_generator import ArticleGenerator
    from blog_engine.seo_optimizer import SEOOptimizer

    print(f"\n記事を生成します...")
    print(f"  キーワード: {args.keyword}")
    print(f"  カテゴリ: {args.category}")
    print()

    generator = ArticleGenerator(config, prompts)
    article = generator.generate_article(keyword=args.keyword, category=args.category)

    print(f"記事生成完了!")
    print(f"  タイトル: {article.get('title', '不明')}")
    print(f"  保存先: {article.get('file_path', '不明')}")

    optimizer = SEOOptimizer(config)
    seo_result = optimizer.check_seo_score(article)
    print(f"  SEOスコア: {seo_result.get('total_score', '不明')}")
    print()


def cmd_schedule(args, config, prompts):
    """スケジューラーを起動する"""
    from blog_engine.scheduler import BlogScheduler

    print("\nスケジューラーを起動します")
    print(f"  投稿時刻: {config.SCHEDULE_HOURS}")
    print(f"  1日の記事数: {config.ARTICLES_PER_DAY}")
    print("  停止するには Ctrl+C を押してください")
    print()

    scheduler = BlogScheduler(config, prompts)
    scheduler.start()


def cmd_build(args, config, prompts):
    """サイトをビルドする"""
    from blog_engine.site_generator import SiteGenerator

    print("\nサイトをビルドします...")
    generator = SiteGenerator(config)
    generator.build_site()
    print("サイトビルド完了!")
    print()


def cmd_keywords(args, config, prompts):
    """キーワードリサーチを実行する"""
    from blog_engine.keyword_researcher import KeywordResearcher

    category = args.category
    count = args.count

    print(f"\nキーワードリサーチを実行します...")
    print(f"  カテゴリ: {category}")
    print(f"  取得件数: {count}")
    print()

    researcher = KeywordResearcher(config, prompts)

    print("--- トレンドキーワード ---")
    keywords = researcher.research_trending_keywords(category, count=count)
    for i, kw in enumerate(keywords, 1):
        print(
            f"  {i:2d}. {kw['keyword']}"
            f"  [ボリューム: {kw.get('volume', '-')}"
            f" | 競合: {kw.get('competition', '-')}"
            f" | タイプ: {kw.get('article_type', '-')}]"
        )
    print()

    if keywords:
        base = keywords[0]["keyword"]
        print(f"--- ロングテールキーワード（ベース: {base}） ---")
        long_tail = researcher.suggest_long_tail_keywords(base)
        for i, lt in enumerate(long_tail, 1):
            print(f"  {i:2d}. {lt}")
        print()

    if keywords:
        base = keywords[0]["keyword"]
        print(f"--- 競合分析（{base}） ---")
        analysis = researcher.analyze_competition(base)
        print(f"  難易度: {analysis.get('difficulty', '-')}/10")
        print(f"  推奨文字数: {analysis.get('recommended_word_count', '-')}文字")
        topics = analysis.get("key_topics", [])
        if topics:
            print("  含めるべきトピック:")
            for t in topics:
                print(f"    - {t}")
        tips = analysis.get("differentiation_tips", [])
        if tips:
            print("  差別化のポイント:")
            for t in tips:
                print(f"    - {t}")
        print()


def cmd_calendar(args, config, prompts):
    """コンテンツカレンダーを生成する"""
    from blog_engine.keyword_researcher import KeywordResearcher

    days = args.days

    print(f"\nコンテンツカレンダーを生成します（{days}日分）...")
    print()

    researcher = KeywordResearcher(config, prompts)
    calendar = researcher.get_content_calendar(days=days)

    print("--- コンテンツカレンダー ---")
    print(f"{'日付':<14} {'カテゴリ':<20} {'キーワード':<30} {'記事タイプ'}")
    print("-" * 80)
    for entry in calendar:
        print(
            f"{entry.get('date', '-'):<14} "
            f"{entry.get('category', '-'):<20} "
            f"{entry.get('keyword', '-'):<30} "
            f"{entry.get('article_type', '-')}"
        )
    print()

    if args.output:
        output_path = args.output
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(calendar, f, ensure_ascii=False, indent=2)
        print(f"カレンダーを保存しました: {output_path}")
        print()


def cmd_deploy(args, config, prompts):
    """GitHub Pagesにデプロイする"""
    from blog_engine.deployer import GitHubPagesDeployer

    print("\nGitHub Pagesにデプロイします...")
    deployer = GitHubPagesDeployer(config)

    status = deployer.check_status()
    print(f"  リポジトリ: {status['repo']}")
    print(f"  ブランチ: {status['branch']}")
    print(f"  公開URL: {status['url']}")
    print()

    result = deployer.deploy()
    print(f"  結果: {result['status']}")
    print(f"  メッセージ: {result['message']}")
    if "url" in result:
        print(f"  URL: {result['url']}")
    print()


def cmd_dashboard(args, config, prompts):
    """ダッシュボードを起動する"""
    import uvicorn
    from blog_engine.dashboard import create_app

    host = getattr(config, "DASHBOARD_HOST", "127.0.0.1")
    port = getattr(config, "DASHBOARD_PORT", 8000)

    print(f"\nダッシュボードを起動します...")
    print(f"  URL: http://{host}:{port}")
    print("  停止するには Ctrl+C を押してください")
    print()

    app = create_app(config, prompts)
    uvicorn.run(app, host=host, port=port)


# ==============================================================
# メインエントリポイント
# ==============================================================

def main():
    """CLIのメインエントリーポイント"""
    parser = argparse.ArgumentParser(
        description="blog_engine - 共通ブログエンジン",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "使用例:\n"
            '  python -m blog_engine.main --config blogs/my-blog/config.py generate --keyword "AI" --category "AI"\n'
            "  python -m blog_engine.main --config blogs/my-blog/config.py build\n"
            "  python -m blog_engine.main --config blogs/my-blog/config.py deploy\n"
            "  python -m blog_engine.main --config blogs/my-blog/config.py schedule\n"
            "  python -m blog_engine.main --config blogs/my-blog/config.py dashboard"
        ),
    )

    parser.add_argument(
        "--config", required=True,
        help="ブログ設定ファイル（config.py）のパス",
    )
    parser.add_argument(
        "--prompts", default=None,
        help="プロンプト設定ファイル（prompts.py）のパス（省略可）",
    )

    subparsers = parser.add_subparsers(dest="command", help="実行するコマンド")

    # generate
    parser_gen = subparsers.add_parser("generate", help="単発で記事を生成する")
    parser_gen.add_argument("--keyword", required=True, help="記事のターゲットキーワード")
    parser_gen.add_argument("--category", required=True, help="記事のカテゴリ")

    # schedule
    subparsers.add_parser("schedule", help="記事自動生成スケジューラーを起動する")

    # build
    subparsers.add_parser("build", help="サイトをビルドする")

    # keywords
    parser_kw = subparsers.add_parser("keywords", help="キーワードリサーチを実行する")
    parser_kw.add_argument("--category", required=True, help="リサーチ対象のカテゴリ")
    parser_kw.add_argument("--count", type=int, default=10, help="取得するキーワード数（デフォルト: 10）")

    # calendar
    parser_cal = subparsers.add_parser("calendar", help="コンテンツカレンダーを生成する")
    parser_cal.add_argument("--days", type=int, default=7, help="カレンダーの日数（デフォルト: 7）")
    parser_cal.add_argument("--output", help="カレンダーをJSONファイルに保存するパス（省略可）")

    # deploy
    subparsers.add_parser("deploy", help="GitHub Pagesにデプロイする")

    # dashboard
    subparsers.add_parser("dashboard", help="ダッシュボードを起動する")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    # config / prompts をロード
    config = load_module(args.config, "blog_config")
    ensure_dirs(config)

    prompts = None
    if args.prompts:
        prompts = load_module(args.prompts, "blog_prompts")
    else:
        # config と同じディレクトリに prompts.py があれば自動読み込み
        config_dir = Path(args.config).resolve().parent
        prompts_path = config_dir / "prompts.py"
        if prompts_path.exists():
            prompts = load_module(str(prompts_path), "blog_prompts")
            logger.info("prompts.py を自動検出しました: %s", prompts_path)

    # コマンド実行
    commands = {
        "generate": cmd_generate,
        "schedule": cmd_schedule,
        "build": cmd_build,
        "keywords": cmd_keywords,
        "calendar": cmd_calendar,
        "deploy": cmd_deploy,
        "dashboard": cmd_dashboard,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args, config, prompts)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
