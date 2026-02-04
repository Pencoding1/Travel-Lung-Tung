from typing import List, Optional, Dict, Any
from pipelines.crawling.base.PipelineBase import BasePipelineCrawler


class VietnamTravelCrawler(BasePipelineCrawler):
    def __init__(self, place_name: str, city_data: Dict = None, **kwargs):
        super().__init__(**kwargs)
        self.place_name = place_name
        self.city_data = city_data or {}
        self.webpage_name = "vietnam_travel"
        self.results_data = []

    def get_domain_name(self) -> str:
        return self.webpage_name

    def get_css_selectors(self) -> List[str]:
        # vietnam.travel sử dụng các class rất trực quan cho nội dung bài viết
        return [
            "article p",
            ".node-article p",
            "h1", "h2", "h3",
            '.node-article__content',
            '.node-destination__content',
            '.field-items',
            '.article-content',
            '.pane-content'
        ]

    def get_place_patterns(self) -> List[str]:
        # Ưu tiên pattern từ city_data để focus vào khu vực miền Nam/HCM
        if "place_patterns" in self.city_data:
            return self.city_data["place_patterns"]

        slug = self.place_name.lower().replace(" ", "-")
        return [f"*/places-to-go/*{slug}*", "*/things-to-do/*"]

    def get_specific_keywords(self) -> List[str]:
        return [self.place_name, "travel", "culture", "experience", "food", "destination"]

    def get_excluded_selectors(self) -> List[str]:
        # Loại bỏ các thành phần điều hướng và quảng cáo của trang
        return [
            ".main-menu",
            ".footer",
            ".social-share",
            ".related-articles",
            ".breadcrumb",
            ".language-switcher"
        ]

