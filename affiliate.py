"""blog_engine - アフィリエイトリンク自動挿入モジュール"""
import logging

logger = logging.getLogger(__name__)


class AffiliateManager:
    """アフィリエイトリンクの管理と自動挿入を行うクラス"""

    def __init__(self, config):
        self.links = getattr(config, 'AFFILIATE_LINKS', {})
        self.amazon_tag = getattr(config, 'AFFILIATE_TAG', '')
        self.adsense_id = getattr(config, 'ADSENSE_CLIENT_ID', '')
        self.adsense_enabled = bool(self.adsense_id)

    def insert_affiliate_links(self, article: dict) -> dict:
        content = article.get("content", "")
        category = article.get("category", "")
        keyword = article.get("keyword", "")

        relevant_links = self._find_relevant_links(category, keyword)

        if relevant_links:
            affiliate_section = self._build_affiliate_section(relevant_links)
            if "## まとめ" in content:
                content = content.replace("## まとめ", f"{affiliate_section}\n\n## まとめ")
            else:
                content += f"\n\n{affiliate_section}"
            article["content"] = content
            article["has_affiliate"] = True
            article["affiliate_count"] = len(relevant_links)
            logger.info(f"{len(relevant_links)}件のアフィリエイトリンクを挿入しました")
        else:
            article["has_affiliate"] = False
            article["affiliate_count"] = 0

        return article

    def _find_relevant_links(self, category: str, keyword: str) -> list:
        relevant = []
        for link_category, links in self.links.items():
            if (link_category in category or link_category in keyword or category in link_category):
                relevant.extend(links)

        if "書籍" in self.links and not any(l.get("service") == "Amazon" for l in relevant):
            relevant.extend(self.links["書籍"])

        seen = set()
        unique = []
        for link in relevant:
            if link["service"] not in seen:
                seen.add(link["service"])
                unique.append(link)

        return unique[:5]

    def _build_affiliate_section(self, links: list) -> str:
        section = "## おすすめサービス・ツール\n\n"
        section += "この記事で紹介した内容を実践するために、以下のサービスがおすすめです。\n\n"

        for link in links:
            url = link["url"]
            if "amazon" in url.lower() and self.amazon_tag:
                separator = "&" if "?" in url else "?"
                url = f"{url}{separator}tag={self.amazon_tag}"
            section += f"- **[{link['service']}]({url})** - {link['description']}\n"

        section += "\n*※ 上記リンクからご利用いただくと、サイト運営の支援になります。*\n"
        return section

    def get_adsense_head_tag(self) -> str:
        if not self.adsense_enabled:
            return ""
        return f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={self.adsense_id}" crossorigin="anonymous"></script>'

    def get_adsense_article_ad(self) -> str:
        if not self.adsense_enabled:
            return ""
        return f"""
<div style="text-align:center;margin:24px 0;">
  <ins class="adsbygoogle" style="display:block"
       data-ad-client="{self.adsense_id}" data-ad-slot="auto"
       data-ad-format="auto" data-full-width-responsive="true"></ins>
  <script>(adsbygoogle = window.adsbygoogle || []).push({{}});</script>
</div>"""
