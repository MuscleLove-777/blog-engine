"""blog_engine - SEO最適化モジュール"""

import logging
import re

logger = logging.getLogger(__name__)


class SEOOptimizer:
    """記事のSEO最適化を分析・支援するクラス"""

    def __init__(self, config) -> None:
        self.config = config
        self.min_keyword_density = getattr(config, 'MIN_KEYWORD_DENSITY', 1.0)
        self.max_keyword_density = getattr(config, 'MAX_KEYWORD_DENSITY', 3.0)
        self.meta_description_length = getattr(config, 'META_DESCRIPTION_LENGTH', 120)
        self.max_article_length = getattr(config, 'MAX_ARTICLE_LENGTH', 3000)
        self.min_seo_score = getattr(config, 'MIN_SEO_SCORE', 70)
        logger.info("SEOOptimizer を初期化しました")

    def analyze_keyword_density(self, content: str, keyword: str) -> float:
        if not content or not keyword:
            return 0.0
        plain_text = self._strip_markdown(content)
        if len(plain_text) == 0:
            return 0.0
        count = plain_text.lower().count(keyword.lower())
        density = (count * len(keyword)) / len(plain_text) * 100
        return round(density, 2)

    def optimize_meta_description(self, description: str) -> str:
        if not description:
            return ""
        optimized = re.sub(r"\s+", " ", description.strip())
        if len(optimized) > self.meta_description_length:
            optimized = optimized[: self.meta_description_length - 3] + "..."
        return optimized

    def check_seo_score(self, article: dict) -> dict:
        details = {}
        recommendations = []
        keyword = article.get("keyword", "")
        title = article.get("title", "")
        content = article.get("content", "")
        meta_description = article.get("meta_description", "")

        # 1. タイトル評価（25点満点）
        title_score = 0
        title_length = len(title)
        if 20 <= title_length <= 35:
            title_score += 15
        elif 10 <= title_length <= 45:
            title_score += 10
        elif title_length > 0:
            title_score += 5
        if keyword and keyword.lower() in title.lower():
            title_score += 10
        details["title"] = {"score": title_score, "max": 25, "length": title_length}

        # 2. 見出し構造評価（20点満点）
        heading_score = 0
        h2_count = len(re.findall(r"^## ", content, re.MULTILINE))
        h3_count = len(re.findall(r"^### ", content, re.MULTILINE))
        if h2_count >= 3:
            heading_score += 10
        elif h2_count >= 1:
            heading_score += 5
        if h3_count >= 2:
            heading_score += 10
        elif h3_count >= 1:
            heading_score += 5
        details["headings"] = {"score": heading_score, "max": 20, "h2_count": h2_count, "h3_count": h3_count}

        # 3. キーワード密度評価（20点満点）
        kw_score = 0
        if keyword:
            density = self.analyze_keyword_density(content, keyword)
            if self.min_keyword_density <= density <= self.max_keyword_density:
                kw_score = 20
            elif 0.5 <= density <= 4.0:
                kw_score = 12
            elif density > 0:
                kw_score = 5
            details["keyword_density"] = {"score": kw_score, "max": 20, "density": density}
        else:
            kw_score = 10
            details["keyword_density"] = {"score": kw_score, "max": 20}

        # 4. メタディスクリプション評価（20点満点）
        meta_score = 0
        meta_length = len(meta_description)
        if 50 <= meta_length <= self.meta_description_length:
            meta_score += 15
        elif 0 < meta_length <= 150:
            meta_score += 8
        if keyword and keyword.lower() in meta_description.lower():
            meta_score += 5
        details["meta_description"] = {"score": meta_score, "max": 20, "length": meta_length}

        # 5. コンテンツ長評価（15点満点）
        content_score = 0
        content_length = len(self._strip_markdown(content))
        if content_length >= self.max_article_length:
            content_score = 15
        elif content_length >= self.max_article_length * 0.7:
            content_score = 10
        elif content_length >= self.max_article_length * 0.4:
            content_score = 5
        elif content_length > 0:
            content_score = 2
        details["content_length"] = {"score": content_score, "max": 15, "length": content_length}

        total_score = title_score + heading_score + kw_score + meta_score + content_score

        return {
            "total_score": total_score,
            "max_score": 100,
            "grade": self._score_to_grade(total_score),
            "details": details,
            "recommendations": recommendations,
        }

    @staticmethod
    def _strip_markdown(text: str) -> str:
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        text = re.sub(r"`[^`]+`", "", text)
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", "", text)
        text = re.sub(r"^[\s]*[-*+]\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"^[\s]*\d+\.\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"^[-*_]{3,}$", "", text, flags=re.MULTILINE)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _score_to_grade(score: int) -> str:
        if score >= 90:
            return "S"
        elif score >= 75:
            return "A"
        elif score >= 60:
            return "B"
        elif score >= 40:
            return "C"
        else:
            return "D"
