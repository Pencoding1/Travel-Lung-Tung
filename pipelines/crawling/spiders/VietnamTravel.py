import os
import json
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

    def _generate_filename(self, stt: Any, ext: str) -> str:
        # Trang này chủ yếu là tiếng Anh, lưu hậu tố _en
        topic = getattr(self, 'topic_keyword', 'general_scan')
        return f"{self.place_name}_{topic}_{self.webpage_name}_en_{stt}.{ext}"

    def save_item_to_disk(self, data: Dict, folder: str):
        # Lưu file theo cấu trúc dự án Travel-Lung-Tung
        path = os.path.join(folder, self.get_domain_name(), self.place_name)
        os.makedirs(path, exist_ok=True)

        stt = len(self.results_data) + 1
        filename_md = self._generate_filename(stt, "md")

        with open(os.path.join(path, filename_md), "w", encoding="utf-8") as f:
            f.write(data['content'])

        json_meta = {
            "stt": stt,
            "filename": filename_md,
            "url": data.get("url"),
            "source": data.get("source")
        }
        self.results_data.append(json_meta)
        print(f"Saved content: {filename_md}")


    async def execute(self, start_url: str, output_folder: str = "../data"):
        await super().execute(start_url, output_folder)
        if self.results_data:
            summary_path = os.path.join(output_folder, "crawled_data", self.get_domain_name(), self.place_name)
            os.makedirs(summary_path, exist_ok=True)

            filename_list = self._generate_filename("List", "json")
            with open(os.path.join(summary_path, filename_list), "w", encoding="utf-8") as f:
                json.dump(self.results_data, f, indent=4, ensure_ascii=False)
