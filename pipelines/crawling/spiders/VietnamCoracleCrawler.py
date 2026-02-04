from typing import List, Optional, Dict, Any
from pipelines.crawling.base.PipelineBase import BasePipelineCrawler


class VietnamCoracleCrawler(BasePipelineCrawler):
    def __init__(self, place_name: str, city_data: Dict = None, **kwargs):
        super().__init__(**kwargs)
        self.place_name = place_name
        self.city_data = city_data or {}
        self.webpage_name = "vietnamcoracle"
        self.results_data = []

    def get_domain_name(self) -> str:
        return self.webpage_name

    def get_css_selectors(self) -> List[str]:
        # Vietnam Coracle thường dùng các class bài viết chuẩn WordPress
        return [
            '.entry-content',
            '.post-content',
            'article.post',
            '.entry-inner',
            '#content'
        ]

    def get_place_patterns(self) -> List[str]:
        # Khóa link theo địa danh để không cào lan sang các vùng khác
        if "place_patterns" in self.city_data:
            return self.city_data["place_patterns"]

        slug = self.place_name.lower().replace(" ", "-")
        # Trang này thường dùng slug tên địa danh trực tiếp trong URL
        return [f"*{slug}*", "*/category/vietnam/*"]

    #def get_embedding_query(self) -> str:
        # AI tập trung lấy nội dung bài review, hướng dẫn du lịch
    #    return f"Các bài viết review du lịch, hướng dẫn đường đi và trải nghiệm tại {self.place_name}"

    def get_specific_keywords(self) -> List[str]:
        return [self.place_name, "guide", "review", "travel", "motorcycle", "stay"]

    def get_excluded_selectors(self) -> List[str]:
        # Loại bỏ sidebar, comment và footer để lấy Markdown sạch
        return [
            ".sidebar",
            "#comments",
            ".author-bio",
            ".sharedaddy",
            ".jp-relatedposts",
            ".footer-widgets",
            "header.entry-header"
        ]

    def get_js_action(self) -> Optional[str]:
        # Vietnam Coracle tải khá nhanh, chủ yếu cần cuộn để load ảnh lười (lazy-load)
        return """
        async () => {
            window.scrollBy(0, 1000);
            await new Promise(r => setTimeout(r, 500));
            window.scrollBy(0, 2000);
            await new Promise(r => setTimeout(r, 500));
        };
        """
