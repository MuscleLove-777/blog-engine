"""blog_engine - 静的サイト生成エンジン

テーマカラーはconfig.THEMEから動的にテンプレートへ注入される。
"""

import json
import math
import re
import shutil
import urllib.parse
from datetime import datetime
from pathlib import Path

import markdown
from jinja2 import Environment, FileSystemLoader


class SiteGenerator:
    """静的サイト生成クラス"""

    ARTICLES_PER_PAGE = 10

    def __init__(self, config):
        self.config = config
        self.base_dir = Path(config.BASE_DIR)

        template_dir = Path(__file__).parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=True,
        )

        self.articles_dir = self.base_dir / "output" / "articles"
        self.output_dir = self.base_dir / "output" / "site"

        self.md = markdown.Markdown(
            extensions=["toc", "fenced_code", "tables", "meta"],
            extension_configs={"toc": {"title": "目次", "toc_depth": "2-3"}},
        )

        self.theme = getattr(config, "THEME", {})

    def build_site(self):
        print(f"[サイト生成] 開始 - 出力先: {self.output_dir}")

        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        (self.output_dir / "articles").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "category").mkdir(parents=True, exist_ok=True)

        articles = self._load_articles()
        if not articles:
            print("[サイト生成] 記事が見つかりません。空のサイトを生成します。")

        articles.sort(key=lambda a: a.get("date", ""), reverse=True)
        print(f"[サイト生成] 記事数: {len(articles)}")

        for article in articles:
            html = self._render_article(article)
            slug = article.get("slug", article.get("id", "untitled"))
            output_path = self.output_dir / "articles" / f"{slug}.html"
            output_path.write_text(html, encoding="utf-8")
            print(f"  記事生成: {slug}.html")

        total_pages = max(1, math.ceil(len(articles) / self.ARTICLES_PER_PAGE))
        for page_num in range(1, total_pages + 1):
            start = (page_num - 1) * self.ARTICLES_PER_PAGE
            end = start + self.ARTICLES_PER_PAGE
            page_articles = articles[start:end]

            html = self._render_index(
                page_articles, articles=articles,
                current_page=page_num, total_pages=total_pages,
            )
            if page_num == 1:
                (self.output_dir / "index.html").write_text(html, encoding="utf-8")
            else:
                page_dir = self.output_dir / "page"
                page_dir.mkdir(parents=True, exist_ok=True)
                (page_dir / f"{page_num}.html").write_text(html, encoding="utf-8")

        print(f"  インデックス生成: {total_pages} ページ")

        categories = self._group_by_category(articles)
        for category, cat_articles in categories.items():
            html = self._render_category(category, cat_articles)
            safe_name = self._slugify(category)
            output_path = self.output_dir / "category" / f"{safe_name}.html"
            output_path.write_text(html, encoding="utf-8")
            print(f"  カテゴリ生成: {category} ({len(cat_articles)} 記事)")

        self._generate_sitemap(articles)
        print("  サイトマップ生成: sitemap.xml")

        self._generate_rss(articles)
        print("  RSSフィード生成: feed.xml")

        self._generate_verification_files()

        print(f"[サイト生成] 完了 - {self.output_dir}")

    def _load_articles(self) -> list:
        articles = []
        if not self.articles_dir.exists():
            return articles

        for filepath in sorted(self.articles_dir.glob("*.json")):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    article = json.load(f)
                article.setdefault("title", "無題")
                article.setdefault("date", datetime.now().strftime("%Y-%m-%d"))
                article.setdefault("category", "未分類")
                article.setdefault("tags", [])
                article.setdefault("content", "")
                article.setdefault("description", "")
                article.setdefault("slug", filepath.stem)
                articles.append(article)
            except (json.JSONDecodeError, IOError) as e:
                print(f"  [警告] 記事読み込みエラー: {filepath} - {e}")

        return articles

    def _get_common_context(self) -> dict:
        config = self.config
        return {
            "blog_name": config.BLOG_NAME,
            "blog_description": config.BLOG_DESCRIPTION,
            "blog_url": config.BLOG_URL,
            "blog_language": getattr(config, "BLOG_LANGUAGE", "ja"),
            "theme": self.theme,
            "google_analytics_id": getattr(config, "GOOGLE_ANALYTICS_ID", ""),
            "adsense_enabled": getattr(config, "ADSENSE_ENABLED", False),
            "adsense_client_id": getattr(config, "ADSENSE_CLIENT_ID", ""),
            "adsense_head": "",
            "adsense_article_ad": "",
        }

    def _render_article(self, article: dict) -> str:
        self.md.reset()
        html_content = self.md.convert(article.get("content", ""))
        toc = getattr(self.md, "toc", "")

        context = self._get_common_context()
        context.update({
            "article": article,
            "content": html_content,
            "toc": toc,
            "related": article.get("related", []),
        })

        template = self.env.get_template("article.html")
        return template.render(**context)

    def _render_index(self, page_articles, articles=None, current_page=1, total_pages=1):
        if articles is None:
            articles = page_articles

        context = self._get_common_context()
        context.update({
            "articles": page_articles,
            "categories": self._group_by_category(articles),
            "current_page": current_page,
            "total_pages": total_pages,
        })

        template = self.env.get_template("index.html")
        return template.render(**context)

    def _render_category(self, category, articles):
        context = self._get_common_context()
        context.update({
            "category": category,
            "articles": articles,
            "article_count": len(articles),
        })

        template = self.env.get_template("category.html")
        return template.render(**context)

    def _generate_sitemap(self, articles):
        blog_url = self.config.BLOG_URL
        urls = [{"loc": blog_url, "lastmod": datetime.now().strftime("%Y-%m-%d"),
                 "changefreq": "daily", "priority": "1.0"}]

        for article in articles:
            slug = article.get("slug", "untitled")
            urls.append({
                "loc": f"{blog_url}/articles/{slug}.html",
                "lastmod": article.get("date", datetime.now().strftime("%Y-%m-%d")),
                "changefreq": "monthly", "priority": "0.8",
            })

        for category in self._group_by_category(articles):
            safe_name = self._slugify(category)
            urls.append({
                "loc": f"{blog_url}/category/{safe_name}.html",
                "lastmod": datetime.now().strftime("%Y-%m-%d"),
                "changefreq": "weekly", "priority": "0.6",
            })

        lines = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        for url in urls:
            lines.append("  <url>")
            lines.append(f"    <loc>{url['loc']}</loc>")
            lines.append(f"    <lastmod>{url['lastmod']}</lastmod>")
            lines.append(f"    <changefreq>{url['changefreq']}</changefreq>")
            lines.append(f"    <priority>{url['priority']}</priority>")
            lines.append("  </url>")
        lines.append("</urlset>")

        (self.output_dir / "sitemap.xml").write_text("\n".join(lines), encoding="utf-8")

    def _generate_rss(self, articles):
        blog_url = self.config.BLOG_URL
        now = datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0900")

        lines = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
                 "  <channel>",
                 f"    <title>{self._escape_xml(self.config.BLOG_NAME)}</title>",
                 f"    <link>{blog_url}</link>",
                 f"    <description>{self._escape_xml(self.config.BLOG_DESCRIPTION)}</description>",
                 f"    <language>{getattr(self.config, 'BLOG_LANGUAGE', 'ja')}</language>",
                 f"    <lastBuildDate>{now}</lastBuildDate>",
                 f'    <atom:link href="{blog_url}/feed.xml" rel="self" type="application/rss+xml"/>']

        for article in articles[:20]:
            slug = article.get("slug", "untitled")
            link = f"{blog_url}/articles/{slug}.html"
            lines.append("    <item>")
            lines.append(f"      <title>{self._escape_xml(article.get('title', ''))}</title>")
            lines.append(f"      <link>{link}</link>")
            lines.append(f"      <guid>{link}</guid>")
            lines.append(f"      <description>{self._escape_xml(article.get('description', ''))}</description>")
            lines.append(f"      <category>{self._escape_xml(article.get('category', ''))}</category>")
            date = article.get("date", "")
            if date:
                try:
                    dt = datetime.strptime(date, "%Y-%m-%d")
                    lines.append(f"      <pubDate>{dt.strftime('%a, %d %b %Y 00:00:00 +0900')}</pubDate>")
                except ValueError:
                    pass
            lines.append("    </item>")

        lines.extend(["  </channel>", "</rss>"])
        (self.output_dir / "feed.xml").write_text("\n".join(lines), encoding="utf-8")

    def _generate_verification_files(self):
        """Google Search Console等の認証ファイルをサイトルートに出力"""
        verification_files = getattr(self.config, "SITE_VERIFICATION_FILES", {})
        for filename, content in verification_files.items():
            filepath = self.output_dir / filename
            filepath.write_text(content, encoding="utf-8")
            print(f"  認証ファイル生成: {filename}")

    @staticmethod
    def _group_by_category(articles):
        categories = {}
        for article in articles:
            cat = article.get("category", "未分類")
            categories.setdefault(cat, []).append(article)
        return categories

    @staticmethod
    def _slugify(text):
        slug = re.sub(r"\s+", "-", text.strip())
        return urllib.parse.quote(slug, safe="-_")

    @staticmethod
    def _escape_xml(text):
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )
