import os
import json
from typing import List, Optional, Dict, Any
from pipelines.crawling.base.PipelineBase import BasePipelineCrawler


class VietravelCrawler(BasePipelineCrawler):
    def __init__(self, place_name: str, city_data: Dict = None, **kwargs):
        super().__init__(**kwargs)
        self.place_name = place_name
        self.city_data = city_data or {}
        self.webpage_name = "vietravel"
        self.results_data = []

    def get_domain_name(self) -> str:
        return self.webpage_name

    def get_css_selectors(self) -> List[str]:
        # Các selector đặc thù để lấy nội dung tour và bài viết trên Vietravel
        return [
            '.tour-introduction',
            '.tour-itinerary',
            '.content-news',
            '.box-common-content',
            '.tour-detail-info'
        ]

    def get_place_patterns(self) -> List[str]:
        # Ưu tiên lấy pattern từ main.py truyền vào để lọc sát khu vực
        if "place_patterns" in self.city_data:
            return self.city_data["place_patterns"]
        else:
            slug = self.place_name.lower().replace(" ", "-")
            includes = [f"*{slug}*", "*/tour/*", "*/du-lich/*", "*/trong-nuoc/*"]
            excludes = [
                "!*chau-a*", "!*chau-au*", "!*chau-my*", "!*chau-phi*", "!*chau-uc*",
                "!*nuoc-ngoai*", "!*quoc-te*"
            ]

            return includes + excludes  # Trả về danh sách kết hợp

    #def get_embedding_query(self) -> str:
        # AI sẽ dùng câu này để lọc nội dung đúng chủ đề du lịch
    #    return f"Thông tin tour du lịch, lịch trình tham quan và điểm đến tại {self.place_name} của Vietravel"

    def get_specific_keywords(self) -> List[str]:
        return [self.place_name, "dịch vụ", "tour", "khởi hành"]

    def get_excluded_selectors(self) -> List[str]:
        return [".btn-book-tour", ".hotline-fixed", ".footer-vtv", ".sidebar-tour"]

    def _generate_filename(self, stt: Any, ext: str) -> str:
        topic = getattr(self, 'topic_keyword', 'general_scan')
        return f"{self.place_name}_{topic}_{self.webpage_name}_vi_{stt}.{ext}"

    def save_item_to_disk(self, data: Dict, folder: str):
        path = os.path.join(folder, self.get_domain_name(), self.place_name)
        os.makedirs(path, exist_ok=True)

        stt = len(self.results_data) + 1
        filename_md = self._generate_filename(stt, "md")

        with open(os.path.join(path, filename_md), "w", encoding="utf-8") as f:
            f.write(data['content'])

        data['stt'] = stt
        data['filename'] = filename_md
        self.results_data.append(data)

    async def execute(self, start_url: str, output_folder: str = "./data"):
        await super().execute(start_url, output_folder)
        if self.results_data:
            summary_path = os.path.join(output_folder, "crawled_data", self.get_domain_name(), self.place_name)
            os.makedirs(summary_path, exist_ok=True)

            filename_list = self._generate_filename("List", "json")
            with open(os.path.join(summary_path, filename_list), "w", encoding="utf-8") as f:
                json.dump(self.results_data, f, indent=4, ensure_ascii=False)