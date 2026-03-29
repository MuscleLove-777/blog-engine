"""blog_engine - 管理ダッシュボード

FastAPIベースの管理画面。記事管理・統計・設定の閲覧が可能。
テーマカラーは config.THEME から取得して動的に適用する。
"""

import json
import re
from datetime import datetime, timedelta
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel


def create_app(config, prompts=None):
    """ダッシュボードアプリケーションを生成する

    Args:
        config: ブログ設定モジュール
        prompts: プロンプト設定モジュール（省略可）

    Returns:
        FastAPI: 設定済みのFastAPIアプリ
    """
    app = FastAPI(
        title=f"{config.BLOG_NAME} 管理ダッシュボード",
        version="1.0.0",
    )

    # テーマカラー取得
    theme = getattr(config, "THEME", {})
    primary = theme.get("primary", "#0f3460")
    accent = theme.get("accent", "#e94560")
    dark_bg = theme.get("dark_bg", "#1a1a2e")
    light_bg = theme.get("light_bg", "#f8f9fa")

    # ================================================================
    # リクエストモデル
    # ================================================================

    class GenerateRequest(BaseModel):
        keyword: str
        category: str

    # ================================================================
    # ユーティリティ関数
    # ================================================================

    def _load_articles() -> list[dict]:
        articles = []
        if not config.ARTICLES_DIR.exists():
            return articles
        for f in config.ARTICLES_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                data.setdefault("slug", f.stem)
                articles.append(data)
            except (json.JSONDecodeError, OSError):
                continue
        articles.sort(key=lambda a: a.get("created_at", ""), reverse=True)
        return articles

    def _count_this_month(articles):
        now = datetime.now()
        return sum(
            1 for a in articles
            if a.get("created_at", "")[:7] == now.strftime("%Y-%m")
        )

    def _category_counts(articles):
        counts = {}
        for a in articles:
            cat = a.get("category", "未分類")
            counts[cat] = counts.get(cat, 0) + 1
        return counts

    def _next_schedule():
        now = datetime.now()
        hours = sorted(getattr(config, "SCHEDULE_HOURS", [8, 12, 18]))
        for hour in hours:
            candidate = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if candidate > now:
                return candidate.strftime("%Y-%m-%d %H:%M")
        tomorrow = now + timedelta(days=1)
        return tomorrow.replace(
            hour=hours[0], minute=0, second=0, microsecond=0
        ).strftime("%Y-%m-%d %H:%M")

    def _avg_seo_score(articles):
        scores = [a.get("seo_score", 0) for a in articles if "seo_score" in a]
        return round(sum(scores) / len(scores), 1) if scores else 0.0

    def _markdown_to_html(text: str) -> str:
        lines = text.split("\n")
        html_lines = []
        in_list = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("### "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f"<h3>{stripped[4:]}</h3>")
            elif stripped.startswith("## "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f"<h2>{stripped[3:]}</h2>")
            elif stripped.startswith("# "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f"<h1>{stripped[2:]}</h1>")
            elif stripped.startswith("- ") or stripped.startswith("* "):
                if not in_list:
                    html_lines.append("<ul>")
                    in_list = True
                html_lines.append(f"<li>{stripped[2:]}</li>")
            elif not stripped:
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append("<br>")
            else:
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f"<p>{stripped}</p>")
        if in_list:
            html_lines.append("</ul>")
        result = "\n".join(html_lines)
        result = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", result)
        result = re.sub(r"`(.+?)`", r"<code>\1</code>", result)
        return result

    # ================================================================
    # 共通HTMLパーツ（テーマカラー変数化）
    # ================================================================

    CSS = f"""
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Inter', 'Noto Sans JP', 'Segoe UI', sans-serif;
            background: {light_bg};
            color: #1E293B;
            display: flex;
            min-height: 100vh;
        }}
        .sidebar {{
            width: 250px;
            background: {dark_bg};
            color: #fff;
            padding: 24px 0;
            position: fixed;
            height: 100vh;
            overflow-y: auto;
        }}
        .sidebar h1 {{
            font-size: 18px;
            padding: 0 24px 24px;
            border-bottom: 1px solid {primary};
            margin-bottom: 16px;
        }}
        .sidebar a {{
            display: block;
            color: #94A3B8;
            text-decoration: none;
            padding: 12px 24px;
            font-size: 14px;
            transition: all 0.2s;
        }}
        .sidebar a:hover, .sidebar a.active {{
            color: #fff;
            background: {primary};
            border-left: 3px solid {accent};
        }}
        .main {{
            margin-left: 250px;
            padding: 32px;
            flex: 1;
            width: calc(100% - 250px);
        }}
        .page-title {{
            font-size: 24px;
            font-weight: 700;
            margin-bottom: 24px;
            color: #1E293B;
        }}
        .cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-bottom: 32px;
        }}
        .card {{
            background: #fff;
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }}
        .card-label {{ font-size: 13px; color: #64748B; margin-bottom: 8px; }}
        .card-value {{ font-size: 32px; font-weight: 700; color: {accent}; }}
        .card-sub {{ font-size: 12px; color: #94A3B8; margin-top: 4px; }}
        .table-wrap {{
            background: #fff;
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
            margin-bottom: 32px;
            overflow-x: auto;
        }}
        .table-wrap h2 {{ font-size: 18px; margin-bottom: 16px; color: #1E293B; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
        th {{ text-align: left; padding: 12px; border-bottom: 2px solid #E2E8F0; color: #64748B; font-weight: 600; font-size: 13px; }}
        td {{ padding: 12px; border-bottom: 1px solid #F1F5F9; }}
        tr:hover td {{ background: #F8FAFC; }}
        td a {{ color: {accent}; text-decoration: none; }}
        td a:hover {{ text-decoration: underline; }}
        .badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 600;
            background: {light_bg};
            color: {accent};
        }}
        .article-content {{
            background: #fff;
            border-radius: 12px;
            padding: 32px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
            line-height: 1.8;
            margin-bottom: 32px;
        }}
        .article-content h1, .article-content h2, .article-content h3 {{
            margin: 24px 0 12px;
            color: #1E293B;
        }}
        .meta-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
        .meta-item {{ padding: 16px; background: {light_bg}; border-radius: 8px; }}
        .meta-item dt {{ font-size: 12px; color: #64748B; margin-bottom: 4px; }}
        .meta-item dd {{ font-size: 15px; font-weight: 600; color: #1E293B; }}
        .filter-bar {{ display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }}
        .filter-bar a {{
            padding: 6px 16px; border-radius: 999px; font-size: 13px;
            text-decoration: none; color: #64748B; background: #E2E8F0; transition: all 0.2s;
        }}
        .filter-bar a:hover, .filter-bar a.active {{ background: {accent}; color: #fff; }}
        .settings-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
        .setting-group {{
            background: #fff; border-radius: 12px; padding: 24px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }}
        .setting-group h3 {{
            font-size: 16px; margin-bottom: 16px; color: {accent};
            border-bottom: 2px solid {light_bg}; padding-bottom: 8px;
        }}
        .setting-row {{
            display: flex; justify-content: space-between; padding: 8px 0;
            border-bottom: 1px solid #F1F5F9; font-size: 14px;
        }}
        .setting-row .label {{ color: #64748B; }}
        .setting-row .value {{ font-weight: 600; color: #1E293B; }}
        .btn {{
            display: inline-block; padding: 10px 20px; border-radius: 8px;
            font-size: 14px; font-weight: 600; cursor: pointer; border: none;
            transition: all 0.2s; text-decoration: none;
        }}
        .btn-primary {{ background: {accent}; color: #fff; }}
        .btn-primary:hover {{ opacity: 0.85; }}
        .btn-secondary {{ background: #E2E8F0; color: #1E293B; }}
        .btn-secondary:hover {{ background: #CBD5E1; }}
        .score-bar {{
            width: 100px; height: 8px; background: #E2E8F0;
            border-radius: 4px; overflow: hidden; display: inline-block;
            vertical-align: middle; margin-right: 8px;
        }}
        .score-bar-fill {{ height: 100%; border-radius: 4px; background: {accent}; }}
        @media (max-width: 768px) {{
            .sidebar {{ display: none; }}
            .main {{ margin-left: 0; width: 100%; padding: 16px; }}
            .cards {{ grid-template-columns: 1fr; }}
            .meta-grid {{ grid-template-columns: 1fr; }}
            .settings-grid {{ grid-template-columns: 1fr; }}
        }}
    </style>
    """

    def _sidebar(active: str = "") -> str:
        links = [("/", "ダッシュボード"), ("/articles", "記事一覧"), ("/settings", "設定")]
        items = ""
        for href, label in links:
            cls = ' class="active"' if active == href else ""
            items += f'<a href="{href}"{cls}>{label}</a>\n'
        return f'<nav class="sidebar"><h1>{config.BLOG_NAME}</h1>{items}</nav>'

    def _base(title: str, content: str, active: str = "") -> str:
        return f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} | {config.BLOG_NAME} 管理</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Noto+Sans+JP:wght@400;600;700&display=swap" rel="stylesheet">
    {CSS}
</head>
<body>
    {_sidebar(active)}
    <main class="main">{content}</main>
</body>
</html>"""

    # ================================================================
    # ページエンドポイント
    # ================================================================

    @app.get("/", response_class=HTMLResponse)
    async def dashboard_top():
        articles = _load_articles()
        total = len(articles)
        this_month = _count_this_month(articles)
        cat_counts = _category_counts(articles)
        next_sched = _next_schedule()
        avg_seo = _avg_seo_score(articles)

        cat_cards = ""
        for cat, cnt in cat_counts.items():
            cat_cards += f'<div class="card"><div class="card-label">{cat}</div><div class="card-value">{cnt}</div><div class="card-sub">記事</div></div>'

        latest = articles[:10]
        rows = ""
        for a in latest:
            slug = a.get("slug", "")
            title_text = a.get("title", "無題")
            cat = a.get("category", "未分類")
            created = a.get("created_at", "-")[:10]
            seo = a.get("seo_score", 0)
            seo_pct = min(int(seo), 100)
            rows += f'<tr><td>{created}</td><td><a href="/articles/{slug}">{title_text}</a></td><td><span class="badge">{cat}</span></td><td><span class="score-bar"><span class="score-bar-fill" style="width:{seo_pct}%"></span></span>{seo}</td></tr>'

        content = f"""
        <h1 class="page-title">ダッシュボード</h1>
        <div class="cards">
            <div class="card"><div class="card-label">記事総数</div><div class="card-value">{total}</div><div class="card-sub">全記事</div></div>
            <div class="card"><div class="card-label">今月の記事数</div><div class="card-value">{this_month}</div><div class="card-sub">{datetime.now().strftime('%Y年%m月')}</div></div>
            <div class="card"><div class="card-label">平均SEOスコア</div><div class="card-value">{avg_seo}</div><div class="card-sub">全記事平均</div></div>
            <div class="card"><div class="card-label">次回スケジュール</div><div class="card-value" style="font-size:20px;">{next_sched}</div><div class="card-sub">自動生成予定</div></div>
        </div>
        <h2 class="page-title" style="font-size:18px;">カテゴリ別記事数</h2>
        <div class="cards">{cat_cards}</div>
        <div class="table-wrap">
            <h2>最新記事</h2>
            <table><thead><tr><th>日付</th><th>タイトル</th><th>カテゴリ</th><th>SEOスコア</th></tr></thead>
            <tbody>{rows if rows else '<tr><td colspan="4" style="text-align:center;color:#94A3B8;padding:32px;">まだ記事がありません</td></tr>'}</tbody></table>
        </div>"""
        return HTMLResponse(_base("ダッシュボード", content, active="/"))

    @app.get("/articles", response_class=HTMLResponse)
    async def articles_list(category: Optional[str] = Query(None)):
        articles = _load_articles()
        if category:
            articles = [a for a in articles if a.get("category") == category]
        all_cats = sorted(set(a.get("category", "未分類") for a in _load_articles()))
        filter_links = f'<a href="/articles" class="{"active" if not category else ""}">すべて</a>\n'
        for cat in all_cats:
            active_cls = "active" if category == cat else ""
            filter_links += f'<a href="/articles?category={cat}" class="{active_cls}">{cat}</a>\n'
        rows = ""
        for a in articles:
            slug = a.get("slug", "")
            title_text = a.get("title", "無題")
            cat = a.get("category", "未分類")
            created = a.get("created_at", "-")[:16].replace("T", " ")
            seo = a.get("seo_score", 0)
            seo_pct = min(int(seo), 100)
            rows += f'<tr><td>{created}</td><td><a href="/articles/{slug}">{title_text}</a></td><td><span class="badge">{cat}</span></td><td><span class="score-bar"><span class="score-bar-fill" style="width:{seo_pct}%"></span></span>{seo}</td></tr>'
        content = f"""
        <h1 class="page-title">記事一覧</h1>
        <div class="filter-bar">{filter_links}</div>
        <div class="table-wrap"><table><thead><tr><th>日時</th><th>タイトル</th><th>カテゴリ</th><th>SEOスコア</th></tr></thead>
        <tbody>{rows if rows else '<tr><td colspan="4" style="text-align:center;color:#94A3B8;padding:32px;">記事が見つかりません</td></tr>'}</tbody></table></div>"""
        return HTMLResponse(_base("記事一覧", content, active="/articles"))

    @app.get("/articles/{slug}", response_class=HTMLResponse)
    async def article_detail(slug: str):
        article_path = None
        if config.ARTICLES_DIR.exists():
            for f in config.ARTICLES_DIR.glob("*.json"):
                if slug in f.stem:
                    article_path = f
                    break
        if article_path is None:
            raise HTTPException(status_code=404, detail="記事が見つかりません")
        try:
            article = json.loads(article_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            raise HTTPException(status_code=500, detail="記事の読み込みに失敗しました")

        title_text = article.get("title", "無題")
        content_body = article.get("content", "")
        cat = article.get("category", "未分類")
        keyword = article.get("keyword", "-")
        created = article.get("created_at", "-")
        seo_score = article.get("seo_score", 0)
        meta_desc = article.get("meta_description", "-")
        word_count = len(content_body)
        keyword_density = article.get("keyword_density", 0)
        headings_count = content_body.count("##")
        seo_color = "#22C55E" if seo_score >= 80 else "#EAB308" if seo_score >= 60 else "#EF4444"
        min_kd = getattr(config, "MIN_KEYWORD_DENSITY", 1.0)
        max_kd = getattr(config, "MAX_KEYWORD_DENSITY", 3.0)
        meta_len = getattr(config, "META_DESCRIPTION_LENGTH", 120)

        content = f"""
        <h1 class="page-title">{title_text}</h1>
        <div class="cards">
            <div class="card"><div class="card-label">SEOスコア</div><div class="card-value" style="color:{seo_color}">{seo_score}</div><div class="card-sub">/ 100</div></div>
            <div class="card"><div class="card-label">文字数</div><div class="card-value">{word_count:,}</div><div class="card-sub">文字</div></div>
            <div class="card"><div class="card-label">見出し数</div><div class="card-value">{headings_count}</div><div class="card-sub">個</div></div>
            <div class="card"><div class="card-label">キーワード密度</div><div class="card-value" style="font-size:24px;">{keyword_density}%</div><div class="card-sub">目標: {min_kd}〜{max_kd}%</div></div>
        </div>
        <div class="table-wrap"><h2>メタ情報</h2>
            <div class="meta-grid">
                <div class="meta-item"><dt>カテゴリ</dt><dd>{cat}</dd></div>
                <div class="meta-item"><dt>ターゲットキーワード</dt><dd>{keyword}</dd></div>
                <div class="meta-item"><dt>作成日時</dt><dd>{created}</dd></div>
                <div class="meta-item"><dt>スラッグ</dt><dd>{slug}</dd></div>
            </div>
        </div>
        <div class="table-wrap"><h2>メタディスクリプション</h2>
            <p style="color:#64748B;font-size:14px;line-height:1.6;">{meta_desc}</p>
            <p style="font-size:12px;color:#94A3B8;margin-top:8px;">{len(meta_desc)} 文字（推奨: {meta_len}文字以内）</p>
        </div>
        <div class="article-content"><h2 style="margin-top:0;">記事プレビュー</h2>
            <hr style="border:none;border-top:1px solid #E2E8F0;margin:16px 0;">
            <div>{_markdown_to_html(content_body)}</div>
        </div>
        <a href="/articles" class="btn btn-secondary">記事一覧に戻る</a>"""
        return HTMLResponse(_base(title_text, content, active="/articles"))

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page():
        cats_list = "、".join(config.TARGET_CATEGORIES)
        hours_list = "、".join(f"{h}:00" for h in config.SCHEDULE_HOURS)
        host = getattr(config, "DASHBOARD_HOST", "127.0.0.1")
        port = getattr(config, "DASHBOARD_PORT", 8000)
        min_kd = getattr(config, "MIN_KEYWORD_DENSITY", 1.0)
        max_kd = getattr(config, "MAX_KEYWORD_DENSITY", 3.0)
        meta_len = getattr(config, "META_DESCRIPTION_LENGTH", 120)

        content = f"""
        <h1 class="page-title">設定</h1>
        <div class="settings-grid">
            <div class="setting-group"><h3>ブログ基本設定</h3>
                <div class="setting-row"><span class="label">ブログ名</span><span class="value">{config.BLOG_NAME}</span></div>
                <div class="setting-row"><span class="label">説明</span><span class="value">{config.BLOG_DESCRIPTION}</span></div>
                <div class="setting-row"><span class="label">URL</span><span class="value">{config.BLOG_URL}</span></div>
            </div>
            <div class="setting-group"><h3>記事生成設定</h3>
                <div class="setting-row"><span class="label">文字数目安</span><span class="value">{config.MAX_ARTICLE_LENGTH:,} 文字</span></div>
                <div class="setting-row"><span class="label">1日の記事数</span><span class="value">{config.ARTICLES_PER_DAY} 記事</span></div>
                <div class="setting-row"><span class="label">対象カテゴリ</span><span class="value">{cats_list}</span></div>
            </div>
            <div class="setting-group"><h3>SEO設定</h3>
                <div class="setting-row"><span class="label">最小キーワード密度</span><span class="value">{min_kd}%</span></div>
                <div class="setting-row"><span class="label">最大キーワード密度</span><span class="value">{max_kd}%</span></div>
                <div class="setting-row"><span class="label">メタ説明文の長さ</span><span class="value">{meta_len} 文字</span></div>
            </div>
            <div class="setting-group"><h3>スケジューラー設定</h3>
                <div class="setting-row"><span class="label">投稿スケジュール</span><span class="value">{hours_list}</span></div>
                <div class="setting-row"><span class="label">ダッシュボードホスト</span><span class="value">{host}</span></div>
                <div class="setting-row"><span class="label">ダッシュボードポート</span><span class="value">{port}</span></div>
            </div>
        </div>"""
        return HTMLResponse(_base("設定", content, active="/settings"))

    # ================================================================
    # APIエンドポイント
    # ================================================================

    @app.post("/api/generate")
    async def api_generate(req: GenerateRequest):
        try:
            from .article_generator import ArticleGenerator
            from .seo_optimizer import SEOOptimizer

            generator = ArticleGenerator(config, prompts)
            article = generator.generate_article(keyword=req.keyword, category=req.category)
            seo_result = SEOOptimizer(config).check_seo_score(article)
            article["seo_score"] = seo_result["total_score"]
            return {
                "status": "success", "message": "記事を生成しました",
                "slug": article.get("slug", ""), "title": article.get("title", ""),
                "seo_score": article["seo_score"],
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"記事生成に失敗しました: {str(e)}")

    @app.post("/api/build")
    async def api_build():
        try:
            from .site_generator import SiteGenerator
            SiteGenerator(config).build_site()
            return {"status": "success", "message": "サイトをビルドしました"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"ビルドに失敗しました: {str(e)}")

    @app.get("/api/stats")
    async def api_stats():
        articles = _load_articles()
        monthly = {}
        for a in articles:
            month_key = a.get("created_at", "")[:7]
            if month_key:
                monthly[month_key] = monthly.get(month_key, 0) + 1
        cat_dist = _category_counts(articles)
        avg_seo = _avg_seo_score(articles)
        seo_ranges = {"0-20": 0, "21-40": 0, "41-60": 0, "61-80": 0, "81-100": 0}
        for a in articles:
            score = a.get("seo_score", 0)
            if score <= 20: seo_ranges["0-20"] += 1
            elif score <= 40: seo_ranges["21-40"] += 1
            elif score <= 60: seo_ranges["41-60"] += 1
            elif score <= 80: seo_ranges["61-80"] += 1
            else: seo_ranges["81-100"] += 1
        return {
            "total_articles": len(articles), "this_month": _count_this_month(articles),
            "avg_seo_score": avg_seo, "monthly_trend": dict(sorted(monthly.items())),
            "category_distribution": cat_dist, "seo_score_distribution": seo_ranges,
        }

    return app
