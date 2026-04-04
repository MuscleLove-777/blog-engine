"""製薬ブログ共通 - アイキャッチ画像自動選定モジュール

各ブログのカテゴリ・キーワードに基づき、無料のストック画像URLを返す。
Unsplashの直接リンク（API不要・無料）を使用。
カテゴリに合った画像をプリセットから選定し、記事ごとに異なる画像を返す。
"""
import hashlib
from typing import Optional

# =========================================================================
# Unsplash 無料画像プリセット（API不要、直接リンク）
# 各カテゴリに対して複数のUnsplash写真IDを用意
# ライセンス: Unsplash License (商用利用可・帰属不要)
# =========================================================================

# 製薬・医薬品関連
_PHARMA_IMAGES = [
    "photo-1584308666744-24d5c474f2ae",  # 錠剤・医薬品
    "photo-1587854692152-cbe660dbde88",  # 研究室
    "photo-1576671081837-49000212a370",  # 薬瓶
    "photo-1579684385127-1ef15d508118",  # 医療
    "photo-1532187863486-abf9dbad1b69",  # 医療研究
    "photo-1559757175-5700dde675bc",     # 製薬ラボ
    "photo-1581093458791-9d42e3c2fd45",  # 研究
    "photo-1631549916768-4e9be593fe56",  # 薬品
]

# データ分析・統計関連
_DATA_ANALYSIS_IMAGES = [
    "photo-1551288049-bebda4e38f71",  # データダッシュボード
    "photo-1460925895917-afdab827c52f",  # グラフ・分析
    "photo-1504868584819-f8e8b4b6d7e3",  # データビジュアル
    "photo-1543286386-713bdd548da4",  # コーディング
    "photo-1518186285589-2f7649de83e0",  # プログラミング
    "photo-1526628953301-3e589a6a8b74",  # 統計グラフ
    "photo-1611532736597-de2d4265fba3",  # データ分析
    "photo-1542903660-eedba2cda473",  # 統計
]

# 規制・法規制関連
_REGULATION_IMAGES = [
    "photo-1589829545856-d10d557cf95f",  # 法律・規制
    "photo-1450101499163-c8848c66ca85",  # ビジネス文書
    "photo-1507003211169-0a1dd7228f2d",  # オフィス
    "photo-1554224155-6726b3ff858f",     # 契約書
    "photo-1521791136064-7986c2920216",  # コンプライアンス
    "photo-1568992687947-868a62a9f521",  # 規制文書
    "photo-1507679799987-c73779587ccf",  # ビジネス
    "photo-1454165804606-c3d57bc86b40",  # 文書作業
]

# テクノロジー・DX関連
_TECHNOLOGY_IMAGES = [
    "photo-1488590528505-98d2b5aba04b",  # テクノロジー
    "photo-1518770660439-4636190af475",  # 回路基板
    "photo-1535378917042-10a22c95931a",  # AI
    "photo-1677442135703-1787eea5ce01",  # AI技術
    "photo-1550751827-4bd374c3f58b",     # サイバー
    "photo-1451187580459-43490279c0fa",  # デジタル
    "photo-1526374965328-7f61d4dc18c5",  # コード
    "photo-1558494949-ef010cbdcc31",     # ネットワーク
]

# 安全性・ファーマコビジランス関連
_SAFETY_IMAGES = [
    "photo-1576091160550-2173dba999ef",  # 医療安全
    "photo-1530026405186-ed1f139313f8",  # 安全管理
    "photo-1559757148-5c350d0d3c56",     # 警告
    "photo-1581056771107-24ca5f033842",  # 医薬品管理
    "photo-1516549655169-df83a0774514",  # 研究ラボ
    "photo-1585435557343-3b092031a831",  # 医療機器
    "photo-1578496479914-7ef3b0193be3",  # 実験室
    "photo-1628771065518-0d82f1938462",  # 安全性
]

# CDISC・臨床データ標準関連
_CLINICAL_DATA_IMAGES = [
    "photo-1504868584819-f8e8b4b6d7e3",  # データ
    "photo-1460925895917-afdab827c52f",  # 分析
    "photo-1543286386-713bdd548da4",  # コーディング
    "photo-1551288049-bebda4e38f71",  # ダッシュボード
    "photo-1526628953301-3e589a6a8b74",  # グラフ
    "photo-1581093458791-9d42e3c2fd45",  # 研究
    "photo-1532187863486-abf9dbad1b69",  # 医療研究
    "photo-1587854692152-cbe660dbde88",  # ラボ
]

# ブログ別カテゴリマッピング
BLOG_IMAGE_MAP = {
    "CDISC Standards Navigator": {
        "_default": _CLINICAL_DATA_IMAGES,
        "SDTM実装ガイド": _CLINICAL_DATA_IMAGES,
        "ADaM設計パターン": _DATA_ANALYSIS_IMAGES,
        "Define-XML": _CLINICAL_DATA_IMAGES,
        "Pinnacle 21・バリデーション": _DATA_ANALYSIS_IMAGES,
        "CDISC最新アップデート": _PHARMA_IMAGES,
        "規制当局対応": _REGULATION_IMAGES,
        "SASコード実践": _DATA_ANALYSIS_IMAGES,
        "海外トレンド翻訳": _PHARMA_IMAGES,
    },
    "FDA規制インサイト": {
        "_default": _REGULATION_IMAGES,
        "FDA承認プロセス": _REGULATION_IMAGES,
        "FDAガイダンス文書": _REGULATION_IMAGES,
        "Warning Letter分析": _REGULATION_IMAGES,
        "PMDA vs FDA比較": _REGULATION_IMAGES,
        "FDA最新ニュース": _PHARMA_IMAGES,
        "eCTD・電子申請": _TECHNOLOGY_IMAGES,
        "バイオ医薬品規制": _PHARMA_IMAGES,
        "海外トレンド翻訳": _PHARMA_IMAGES,
    },
    "臨床統計ラボ": {
        "_default": _DATA_ANALYSIS_IMAGES,
        "SAS実践テクニック": _DATA_ANALYSIS_IMAGES,
        "R for Clinical Trials": _DATA_ANALYSIS_IMAGES,
        "統計解析計画書・SAP": _DATA_ANALYSIS_IMAGES,
        "生存時間解析": _DATA_ANALYSIS_IMAGES,
        "混合効果モデル": _DATA_ANALYSIS_IMAGES,
        "ICH E9(R1) Estimand": _REGULATION_IMAGES,
        "臨床統計最新ニュース": _PHARMA_IMAGES,
        "海外トレンド翻訳": _PHARMA_IMAGES,
    },
    "ファーマコビジランス最前線": {
        "_default": _SAFETY_IMAGES,
        "副作用報告・ICSR": _SAFETY_IMAGES,
        "シグナル検出": _DATA_ANALYSIS_IMAGES,
        "PBRER/PSUR/DSUR": _REGULATION_IMAGES,
        "MedDRAコーディング": _CLINICAL_DATA_IMAGES,
        "PV最新ニュース": _PHARMA_IMAGES,
        "各国PV規制比較": _REGULATION_IMAGES,
        "リスクマネジメント・RMP": _SAFETY_IMAGES,
        "海外トレンド翻訳": _PHARMA_IMAGES,
    },
    "製薬DXジャーナル": {
        "_default": _TECHNOLOGY_IMAGES,
        "AI創薬・機械学習": _TECHNOLOGY_IMAGES,
        "DCT（分散型臨床試験）": _PHARMA_IMAGES,
        "RWD/RWE活用": _DATA_ANALYSIS_IMAGES,
        "クラウド・データ基盤": _TECHNOLOGY_IMAGES,
        "CSV・規制対応DX": _REGULATION_IMAGES,
        "製薬DX最新ニュース": _TECHNOLOGY_IMAGES,
        "デジタルバイオマーカー": _TECHNOLOGY_IMAGES,
        "海外トレンド翻訳": _PHARMA_IMAGES,
    },
}

# Unsplash画像のベースURL（API不要）
_UNSPLASH_BASE = "https://images.unsplash.com"


def get_eyecatch_url(
    blog_name: str,
    category: str,
    keyword: str = "",
    slug: str = "",
    width: int = 1200,
    height: int = 630,
) -> str:
    """記事のカテゴリ・キーワードに基づきアイキャッチ画像URLを返す。

    Args:
        blog_name: ブログ名（config.BLOG_NAME）
        category: 記事のカテゴリ
        keyword: 記事のキーワード（画像選定のバリエーション用）
        slug: 記事のスラグ（画像選定のバリエーション用）
        width: 画像の幅（デフォルト1200）
        height: 画像の高さ（デフォルト630）

    Returns:
        アイキャッチ画像のURL文字列
    """
    # ブログ → カテゴリ → 画像リスト
    blog_map = BLOG_IMAGE_MAP.get(blog_name, {})
    images = blog_map.get(category, blog_map.get("_default", _PHARMA_IMAGES))

    # キーワード+スラグからハッシュを計算し、画像を決定論的に選択
    seed = f"{blog_name}:{category}:{keyword}:{slug}"
    hash_val = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    selected = images[hash_val % len(images)]

    # Unsplash直接リンク（API不要、無料、商用利用可）
    return f"{_UNSPLASH_BASE}/{selected}?w={width}&h={height}&fit=crop&auto=format&q=80"


def get_eyecatch_credit() -> str:
    """画像クレジット文字列を返す（Unsplash規約対応）"""
    return "Photo from [Unsplash](https://unsplash.com/)"


def add_eyecatch_to_article(article: dict, blog_name: str) -> dict:
    """記事辞書にアイキャッチ画像情報を追加する。

    article辞書に以下のキーを追加:
    - eyecatch_url: 画像URL
    - eyecatch_credit: クレジット表記

    また、content（Markdown本文）の先頭にアイキャッチ画像を挿入する。

    Args:
        article: 記事辞書（title, content, category, keyword, slug等）
        blog_name: ブログ名

    Returns:
        画像情報が追加された記事辞書
    """
    category = article.get("category", "")
    keyword = article.get("keyword", "")
    slug = article.get("slug", "")

    url = get_eyecatch_url(
        blog_name=blog_name,
        category=category,
        keyword=keyword,
        slug=slug,
    )
    credit = get_eyecatch_credit()

    article["eyecatch_url"] = url
    article["eyecatch_credit"] = credit

    # Markdown本文の先頭にアイキャッチ画像を挿入
    content = article.get("content", "")
    eyecatch_md = f"![{article.get('title', 'アイキャッチ画像')}]({url})\n\n*{credit}*\n\n"

    # もし本文が見出し(#)で始まる場合、見出しの次に挿入
    lines = content.split("\n", 1)
    if lines and lines[0].startswith("#"):
        heading = lines[0]
        rest = lines[1] if len(lines) > 1 else ""
        article["content"] = f"{heading}\n\n{eyecatch_md}{rest}"
    else:
        article["content"] = f"{eyecatch_md}{content}"

    return article
